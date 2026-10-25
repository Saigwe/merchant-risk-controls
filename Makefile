PY ?= python
DB ?= warehouse/risk.duckdb
FIXTURE_DB ?= warehouse/fixture.duckdb
DBT = cd dbt && DUCKDB_PATH=../$(DB) dbt

.PHONY: all fixture-all bronze bronze-fixture dbt dbt-fixture pytest app clean

all: pytest bronze dbt                            ## 20k merchants, Jan-Dec 2025
fixture-all: pytest                               ## 600 merchants + planted violations (CI)
	$(MAKE) bronze-fixture dbt-fixture DB=$(FIXTURE_DB)
	$(PY) -m py_compile app/streamlit_app.py

pytest:
	$(PY) -m pytest -q tests

bronze:
	$(PY) ingestion/generate_risk_data.py --db $(DB)

bronze-fixture:
	$(PY) ingestion/generate_risk_data.py --db $(DB) --merchants 600 --plant-violations

dbt:
	$(DBT) build --profiles-dir .

dbt-fixture:
	$(DBT) build --profiles-dir . --vars '{is_fixture: true}'

app:
	RISK_DUCKDB_PATH=$(CURDIR)/$(DB) streamlit run app/streamlit_app.py

clean:
	rm -rf warehouse dbt/target dbt/logs
