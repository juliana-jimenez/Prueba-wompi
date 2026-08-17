import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dev_transactions import build_summary, read_transactions

SCRIPT_PATH = Path(__file__).resolve().parent.parent / "dev_transactions.py"


def make_record(id_, created_at, status, bin_, amount, three_ds=True):
    return {
        "id": id_,
        "created_at": created_at,
        "updated_at": created_at,
        "status": status,
        "payment_method_type": {
            "type": "CARD",
            "extra": {
                "bin": bin_,
                "card_holder": "Test Person",
                "is_three_ds": three_ds,
                "unique_code": "ABC123",
                "three_ds_auth_type": "01",
                "external_identifier": "000000",
                "processor_response_code": "00" if status == "APPROVED" else "05",
                "authorizer_transaction_id": "111111111",
            },
            "installments": 1,
        },
        "amount_in_cents": amount,
    }


@pytest.fixture
def sample_records():
    return [
        make_record("1", "2024-04-01 10:00:00", "APPROVED", "400490", 1000),
        make_record("2", "2024-04-01 11:00:00", "APPROVED", "400490", 2000),
        make_record("3", "2024-04-01 12:00:00", "DECLINED", "400490", 5000),
        make_record("4", "2024-04-01 09:00:00", "APPROVED", "512069", 3000),
        make_record("5", "2024-04-02 09:00:00", "APPROVED", "400490", 700),
        make_record("6", "2024-04-01 13:00:00", "ERROR", "999999", 999),
    ]


def test_build_summary_groups_only_approved(sample_records):
    df = pd.DataFrame(sample_records)
    summary = build_summary(df)

    # Bins with only DECLINED/ERROR transactions must not appear.
    assert "999999" not in summary["bin"].values

    row = summary[
        (summary["year"] == 2024)
        & (summary["month"] == 4)
        & (summary["day"] == 1)
        & (summary["bin"] == "400490")
    ].iloc[0]
    assert row["approved_transactions_count"] == 2
    assert row["approved_total_amount"] == 3000


def test_build_summary_separates_days(sample_records):
    df = pd.DataFrame(sample_records)
    summary = build_summary(df)

    day1 = summary[(summary["day"] == 1) & (summary["bin"] == "400490")].iloc[0]
    day2 = summary[(summary["day"] == 2) & (summary["bin"] == "400490")].iloc[0]
    assert day1["approved_transactions_count"] == 2
    assert day2["approved_transactions_count"] == 1
    assert day2["approved_total_amount"] == 700


def test_build_summary_total_matches_input(sample_records):
    df = pd.DataFrame(sample_records)
    summary = build_summary(df)

    approved_in_input = sum(1 for r in sample_records if r["status"] == "APPROVED")
    assert summary["approved_transactions_count"].sum() == approved_in_input


def test_read_transactions_skips_malformed_lines(tmp_path, sample_records):
    input_path = tmp_path / "input.jsonl"
    lines = [json.dumps(r) for r in sample_records]
    lines.insert(2, "{this is not valid json")
    input_path.write_text("\n".join(lines) + "\n")

    df = read_transactions(input_path)
    assert len(df) == len(sample_records)


def test_read_transactions_raises_on_all_invalid(tmp_path):
    input_path = tmp_path / "input.jsonl"
    input_path.write_text("not json\nalso not json\n")

    with pytest.raises(ValueError):
        read_transactions(input_path)


def test_script_is_idempotent(tmp_path, sample_records):
    input_path = tmp_path / "input.jsonl"
    input_path.write_text("\n".join(json.dumps(r) for r in sample_records) + "\n")

    out1 = tmp_path / "out1.parquet"
    out2 = tmp_path / "out2.parquet"

    for out_path in (out1, out2):
        subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--input", str(input_path), "--output", str(out_path)],
            check=True,
            capture_output=True,
            text=True,
        )

    assert out1.read_bytes() == out2.read_bytes()
