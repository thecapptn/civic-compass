.PHONY: install seed run test clean

install:
	pip install -r requirements.txt

seed:
	python -m app.seed

run: seed
	uvicorn app.main:app --host 0.0.0.0 --port 5021 --reload

test:
	python -m pytest tests -q

clean:
	rm -rf data __pycache__ app/__pycache__ tests/__pycache__ .pytest_cache
