from app.services.query_classifier import QueryClassifier, QueryType


def test_classifier_detects_sql_keywords():
    classifier = QueryClassifier()
    query = "SELECT full_name FROM hr_hr_data WHERE performance_rating >= 4"
    result = classifier.classify(query, structured_tables=["hr_hr_data"])
    assert result == QueryType.SQL


def test_classifier_defaults_to_rag():
    classifier = QueryClassifier()
    query = "Summarize the engineering onboarding process."
    result = classifier.classify(query, structured_tables=[])
    assert result == QueryType.RAG
