.PHONY: run test eval clean

run:
	cd backend && uvicorn src.main:app --reload

test:
	cd backend && pytest tests/ -m "not llm" -v

eval:
	cd backend && python ../eval/run_eval.py --sessions ../dataset_candidate/train/sessions --delay 2
	python dataset_candidate/eval.py --predictions eval/predictions_train.jsonl --labels dataset_candidate/train/labels.jsonl

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	rm -f backend/data/verdicts.db
	rm -f eval/predictions_*.jsonl