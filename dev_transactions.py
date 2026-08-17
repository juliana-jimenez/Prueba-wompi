"""
Genera una vista de resumen a partir de un archivo de transacciones (JSONL).

Uso:
    python dev_transactions.py [--input transactions_50k.jsonl] [--output out_view.parquet]

Agrupa las transacciones aprobadas por día, mes, año y BIN, calculando la
cantidad de transacciones aprobadas y el monto total aprobado (en la unidad
original del archivo: centavos).
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

APPROVED_STATUS = "APPROVED"


def parse_args():
    parser = argparse.ArgumentParser(description="Genera una vista de resumen de transacciones.")
    parser.add_argument(
        "--input",
        default="transactions_50k.jsonl",
        help="Ruta al archivo JSONL de entrada (default: transactions_50k.jsonl)",
    )
    parser.add_argument(
        "--output",
        default="out_view.parquet",
        help="Ruta al archivo Parquet de salida (default: out_view.parquet)",
    )
    return parser.parse_args()


def read_transactions(input_path: Path) -> pd.DataFrame:
    """Lee un archivo JSONL. Las líneas mal formadas se omiten y se reportan
    por stderr, en lugar de abortar todo el procesamiento."""
    records = []
    skipped = 0
    with open(input_path, "r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                skipped += 1
                print(f"Advertencia: línea {line_number} inválida, se omite ({exc}).", file=sys.stderr)

    if skipped:
        print(f"Advertencia: se omitieron {skipped} línea(s) inválida(s) de {input_path}.", file=sys.stderr)

    if not records:
        raise ValueError(f"El archivo de entrada '{input_path}' no contiene registros válidos.")

    return pd.DataFrame(records)


def build_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Agrupa únicamente las transacciones aprobadas por año/mes/día/BIN."""
    approved = df[df["status"] == APPROVED_STATUS].copy()

    created_at = pd.to_datetime(approved["created_at"])
    approved["day"] = created_at.dt.day
    approved["month"] = created_at.dt.month
    approved["year"] = created_at.dt.year
    approved["bin"] = approved["payment_method_type"].apply(
        lambda pmt: (pmt or {}).get("extra", {}).get("bin")
    )

    summary = (
        approved.groupby(["year", "month", "day", "bin"], as_index=False)
        .agg(
            approved_transactions_count=("status", "size"),
            approved_total_amount=("amount_in_cents", "sum"),
        )
        .sort_values(["year", "month", "day", "bin"])
        .reset_index(drop=True)
    )

    return summary


def main():
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        print(f"Error: no se encontró el archivo de entrada '{input_path}'.", file=sys.stderr)
        sys.exit(1)

    df = read_transactions(input_path)
    summary = build_summary(df)
    summary.to_parquet(output_path, index=False)

    print(f"Procesadas {len(df)} transacciones.")
    print(f"Vista de resumen generada con {len(summary)} filas -> {output_path}")


if __name__ == "__main__":
    main()
