# Prueba técnica Wompi — Reto 2: Vista de resumen de transacciones

Script en Python que lee un archivo de transacciones (JSONL), las procesa
y genera una vista agregada en formato Parquet.

## Requisitos

- Python 3.9+
- Dependencias listadas en `requirements.txt`

## Instalación

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Para correr los tests, instala además las dependencias de desarrollo:

```bash
pip install -r requirements-dev.txt
```

## Archivo de entrada (`transactions_50k.jsonl`)

**El archivo no está incluido en este repositorio.** Contiene el campo
`payment_method_type.extra.card_holder` con nombres de tarjetahabientes, y
este es un repositorio público — no es buena práctica publicar ese tipo de
dato aunque sea de prueba. Coloca tu copia de `transactions_50k.jsonl` en la
raíz del proyecto (junto a `dev_transactions.py`) antes de ejecutar el
script, o indica su ruta con `--input`.

## Uso

```bash
python dev_transactions.py --input transactions_50k.jsonl --output out_view.parquet
```

Ambos argumentos son opcionales; por defecto usa `transactions_50k.jsonl` como
entrada y `out_view.parquet` como salida.

## Estructura de la vista de salida

Cada fila representa una combinación **año + mes + día + BIN** que tuvo al
menos una transacción aprobada, con las siguientes columnas:

| Columna                        | Descripción                                                        |
|---------------------------------|---------------------------------------------------------------------|
| `year`                          | Año de la transacción (de `created_at`)                            |
| `month`                         | Mes de la transacción                                               |
| `day`                            | Día de la transacción                                               |
| `bin`                            | Bank Identification Number (`payment_method_type.extra.bin`)       |
| `approved_transactions_count`   | Cantidad de transacciones con `status = "APPROVED"`                |
| `approved_total_amount`         | Suma de `amount_in_cents` de las transacciones aprobadas            |

## Supuestos

- **Fecha usada**: se agrupa por `created_at` (fecha de creación de la
  transacción), no por `updated_at`.
- **"Aprobada"**: se considera aprobada toda transacción cuyo campo
  `status` sea exactamente `"APPROVED"`. Los valores observados en el
  dataset son `APPROVED`, `DECLINED` y `ERROR`.
- **Solo transacciones aprobadas generan filas**: el archivo se filtra a
  `status = "APPROVED"` antes de agrupar. Una combinación día/BIN que solo
  tuvo transacciones `DECLINED`/`ERROR` no aparece en la salida (no tiene
  sentido reportar un `approved_total_amount = 0` para un BIN que nunca
  aprobó nada ese día).
- **Monto**: se reporta en la misma unidad del archivo de origen
  (`amount_in_cents`, es decir centavos), sin conversión a unidad monetaria
  mayor, para no perder precisión ni asumir la moneda.
- **BIN**: se extrae de `payment_method_type.extra.bin`. Todos los
  registros del archivo de entrada corresponden a `payment_method_type.type
  = "CARD"`; si existieran otros tipos sin ese campo, esas filas quedarían
  con `bin` nulo y se agruparían aparte.
- **Formato de salida**: Parquet, vía `pandas.DataFrame.to_parquet`
  (requiere `pyarrow`).
- **Líneas mal formadas**: si una línea del JSONL no es JSON válido, se
  omite y se reporta un aviso por `stderr` con el número de línea; el
  procesamiento continúa con el resto del archivo. Solo se aborta si
  ninguna línea del archivo pudo leerse.

## Campos del archivo de entrada

El archivo de entrada tiene esta forma (uniforme en las 50,000 líneas, sin
campos faltantes ni nulos):

```
id, created_at, updated_at, status, amount_in_cents,
payment_method_type: { type, installments,
  extra: { bin, card_holder, is_three_ds, unique_code,
           three_ds_auth_type, external_identifier,
           processor_response_code, authorizer_transaction_id } }
```

Campos usados en la salida: `created_at` (año/mes/día), `status`,
`payment_method_type.extra.bin`, `amount_in_cents`.

Campos presentes en el archivo pero **no usados** en la vista de resumen,
porque el reto no los pide: `id`, `updated_at`, `payment_method_type.type`
(siempre `"CARD"` en este archivo), `installments`, `card_holder`,
`is_three_ds`, `unique_code`, `three_ds_auth_type`, `external_identifier`,
`processor_response_code`, `authorizer_transaction_id`.

Verificaciones hechas sobre el archivo completo antes de definir la lógica:

- `id` es único en las 50,000 filas (no hay duplicados que puedan inflar
  el conteo o el monto).
- `bin` siempre tiene 6 dígitos y siempre está presente.
- `amount_in_cents` siempre es un entero positivo (rango: 150,024 a
  999,655,413), sin nulos ni negativos.
- `status = "APPROVED"` corresponde en el 100% de los casos a
  `processor_response_code = "00"`, lo que confirma que es el campo/valor
  correcto para identificar transacciones aprobadas.
- Rango de fechas de `created_at`: 2024-04-01 a 2024-09-28.

## Idempotencia

El script es puramente funcional: lee el archivo de entrada completo, agrega
en memoria con `pandas.groupby` y sobreescribe el archivo de salida en cada
ejecución. No hay estado compartido entre corridas. Ejecutarlo repetidamente
sobre el mismo archivo de entrada genera un archivo de salida byte-idéntico
(verificado con `md5` en 3 corridas seguidas, y cubierto por
`tests/test_dev_transactions.py::test_script_is_idempotent`).

## Tests

```bash
pytest tests/
```

Cubren: agregación correcta (solo aprobadas, separación correcta por día),
que el total de aprobadas en la salida coincida con el total de entrada,
manejo de líneas JSONL corruptas, y la idempotencia del script ejecutado
como subproceso end-to-end.

## Validación realizada sobre `transactions_50k.jsonl`

- 50,000 registros leídos, 42,427 con `status = APPROVED`.
- 21,529 combinaciones únicas de año/mes/día/BIN con al menos una
  transacción aprobada.
- Suma de `approved_transactions_count` en la salida = 42,427 (coincide con
  el total de transacciones aprobadas en el archivo de entrada).
- Ejecutado varias veces seguidas sobre el mismo archivo de entrada: el
  `.parquet` de salida da el mismo hash MD5 en todas las corridas.
