.PHONY: run test eval clean

# Start the backend server with hot reload
run:
	cd backend && uvicorn src.main:app --reload

# Run all fast tests, excluding LLM integration tests
test:
	cd backend && pytest tests/ -m "not llm" -v

# Run pipeline on train set and print confusion matrix
eval:
	cd backend && python ../eval/run_eval.py --sessions ../dataset_candidate/train/sessions --delay 2
	python dataset_candidate/eval.py --predictions eval/predictions_train.jsonl --labels dataset_candidate/train/labels.jsonl

# Remove pycache, test cache, database, and generated prediction files
clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	rm -f backend/data/verdicts.db
	rm -f eval/predictions_*.jsonl