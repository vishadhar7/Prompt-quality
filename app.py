
import json
import re
import logging
import requests
import pandas as pd

from flask import Flask, render_template, request, jsonify
from sklearn.model_selection import train_test_split

app = Flask(__name__)

OLLAMA_URL = "http://localhost:11434"
DEFAULT_MODEL = "llama3.2:3b"
REQUEST_TIMEOUT = 300

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# --------------------------------------------------
# PROMPT STRATEGIES
# --------------------------------------------------

STRATEGIES = {
    "Direct Instruction": """
Answer the question directly and clearly.
Avoid unnecessary explanations.
""",

    "Step-by-Step": """
Understand the question and solve it step by step.
Present the explanation in a logical sequence.
""",

    "Structured Answer": """
Provide a well-organized answer.
Use headings, bullet points, and examples wherever appropriate.
""",

    "Expert Role": """
Act as a subject matter expert.
Provide an accurate, informative, and professional answer.
"""
}


# --------------------------------------------------
# OLLAMA CONNECTION
# --------------------------------------------------

def ollama_chat(model, prompt, json_mode=False):

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "stream": False
    }

    if json_mode:
        payload["format"] = "json"

    try:
        logger.info("Sending request to Ollama: %s", model)

        response = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json=payload,
            timeout=REQUEST_TIMEOUT
        )

        response.raise_for_status()

        data = response.json()
        answer = data.get("message", {}).get("content", "")

        if not answer:
            raise ValueError("Ollama returned an empty response.")

        return answer.strip()

    except requests.exceptions.ConnectionError:
        raise Exception(
            "Cannot connect to Ollama. Make sure Ollama is running."
        )

    except requests.exceptions.Timeout:
        raise Exception(
            "Ollama request timed out. Try fewer strategies."
        )

    except requests.exceptions.RequestException as e:
        raise Exception(f"Ollama API error: {str(e)}")


# --------------------------------------------------
# JSON EXTRACTION
# --------------------------------------------------

def extract_json(text):

    if not text:
        raise ValueError("Empty evaluator response.")

    text = text.strip()

    text = re.sub(
        r"```json\s*|```",
        "",
        text,
        flags=re.IGNORECASE
    )

    try:
        result = json.loads(text)

        if isinstance(result, dict):
            return result

    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()

    for index, character in enumerate(text):

        if character == "{":

            try:
                result, _ = decoder.raw_decode(text[index:])

                if isinstance(result, dict):
                    return result

            except json.JSONDecodeError:
                continue

    raise ValueError("Invalid JSON from evaluator.")


# --------------------------------------------------
# SCORE NORMALIZATION
# --------------------------------------------------

def normalize_score(value):

    try:
        score = float(value)
        return round(max(0, min(10, score)), 2)

    except (TypeError, ValueError):
        return 0.0


def normalize_evaluation(data):

    accuracy = data.get("accuracy", data.get("correctness", 0))
    relevance = data.get("relevance", data.get("relevancy", 0))
    completeness = data.get("completeness", data.get("coverage", 0))
    clarity = data.get("clarity", data.get("readability", 0))

    scores = {
        "accuracy": normalize_score(accuracy),
        "relevance": normalize_score(relevance),
        "completeness": normalize_score(completeness),
        "clarity": normalize_score(clarity)
    }

    scores["overall"] = round(
        sum(scores.values()) / 4, 2
    )

    feedback = data.get(
        "feedback",
        "No feedback provided."
    )

    if not isinstance(feedback, str):
        feedback = str(feedback)

    return {
        "scores": scores,
        "feedback": feedback,
        "evaluation_valid": True
    }


def fallback_evaluation(reason):

    return {
        "scores": {
            "accuracy": 0,
            "relevance": 0,
            "completeness": 0,
            "clarity": 0,
            "overall": 0
        },
        "feedback": (
            "Evaluation could not be completed: " + str(reason)
        ),
        "evaluation_valid": False
    }


# --------------------------------------------------
# ANSWER GENERATION
# --------------------------------------------------

def generate_answer(question, strategy, model):

    instruction = STRATEGIES.get(
        strategy,
        STRATEGIES["Direct Instruction"]
    )

    prompt = f"""
You are an intelligent AI assistant.

PROMPTING STRATEGY:
{strategy}

INSTRUCTIONS:
{instruction}

USER QUESTION:
{question}

Generate a high-quality answer to the user's question.
"""

    return ollama_chat(
        model=model,
        prompt=prompt
    )


# --------------------------------------------------
# ANSWER EVALUATION
# --------------------------------------------------

def evaluate_answer(
    question,
    reference_answer,
    generated_answer,
    model
):

    prompt = f"""
You are an expert answer evaluation system.

Evaluate the generated answer against the reference answer.

QUESTION:
{question}

REFERENCE ANSWER:
{reference_answer}

GENERATED ANSWER:
{generated_answer}

Give scores from 0 to 10 for:

1. accuracy
2. relevance
3. completeness
4. clarity

Also provide short feedback.

Return ONLY a valid JSON object.
Do not include Markdown or explanations outside JSON.

Use this exact structure:

{{
    "accuracy": 8,
    "relevance": 9,
    "completeness": 8,
    "clarity": 9,
    "feedback": "The answer is relevant and clear."
}}
"""

    try:

        raw_response = ollama_chat(
            model=model,
            prompt=prompt,
            json_mode=True
        )

        logger.info("Evaluator response: %s", raw_response)

        parsed_data = extract_json(raw_response)

        return normalize_evaluation(parsed_data)

    except Exception as e:

        logger.exception("Evaluation failed")

        return fallback_evaluation(str(e))


# --------------------------------------------------
# RUN ONE STRATEGY
# --------------------------------------------------

def run_strategy(
    question,
    reference_answer,
    strategy,
    model
):

    logger.info("Starting strategy: %s", strategy)

    generated_answer = generate_answer(
        question,
        strategy,
        model
    )

    evaluation = evaluate_answer(
        question,
        reference_answer,
        generated_answer,
        model
    )

    return {
        "strategy": strategy,
        "answer": generated_answer,
        "scores": evaluation["scores"],
        "feedback": evaluation["feedback"],
        "evaluation_valid": evaluation["evaluation_valid"]
    }


# --------------------------------------------------
# HOME PAGE
# --------------------------------------------------

@app.route("/")
def home():
    return render_template("index.html")


# --------------------------------------------------
# GET AVAILABLE MODELS
# --------------------------------------------------

@app.route("/api/models", methods=["GET"])
def get_models():

    try:

        response = requests.get(
            f"{OLLAMA_URL}/api/tags",
            timeout=10
        )

        response.raise_for_status()

        data = response.json()

        models = [
            item["name"]
            for item in data.get("models", [])
        ]

        return jsonify({
            "success": True,
            "models": models
        })

    except Exception as e:

        logger.exception("Model retrieval failed")

        return jsonify({
            "success": False,
            "models": [],
            "error": str(e)
        }), 500


# --------------------------------------------------
# MANUAL COMPARISON
# --------------------------------------------------

@app.route("/api/compare", methods=["POST"])
def compare():

    try:

        data = request.get_json(silent=True) or {}

        question = str(data.get("question", "")).strip()

        reference_answer = str(
            data.get("reference_answer", "")
        ).strip()

        model = data.get("model", DEFAULT_MODEL)

        strategies = data.get("strategies", [])

        if not question:
            return jsonify({
                "error": "Please enter a question."
            }), 400

        if not reference_answer:
            return jsonify({
                "error": "Please enter a reference answer."
            }), 400

        if not isinstance(strategies, list):
            return jsonify({
                "error": "Strategies must be a list."
            }), 400

        valid_strategies = [
            item for item in strategies
            if item in STRATEGIES
        ]

        if not valid_strategies:
            return jsonify({
                "error": "Select at least one valid strategy."
            }), 400

        results = []

        for strategy in valid_strategies:

            result = run_strategy(
                question=question,
                reference_answer=reference_answer,
                strategy=strategy,
                model=model
            )

            results.append(result)

        return jsonify({
            "success": True,
            "results": results,
            "note": "Scores are AI-judge estimates."
        })

    except Exception as e:

        logger.exception("Comparison failed")

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# --------------------------------------------------
# DATASET EVALUATION
# --------------------------------------------------

@app.route("/api/evaluate_dataset", methods=["POST"])
def evaluate_dataset():

    try:

        if "file" not in request.files:
            return jsonify({
                "error": "Please upload a CSV dataset."
            }), 400

        file = request.files["file"]

        if not file.filename:
            return jsonify({
                "error": "No file selected."
            }), 400

        if not file.filename.lower().endswith(".csv"):
            return jsonify({
                "error": "Please upload a CSV file."
            }), 400

        df = pd.read_csv(file)

        required_columns = [
            "question",
            "reference_answer"
        ]

        for column in required_columns:

            if column not in df.columns:
                return jsonify({
                    "error": (
                        f"Dataset must contain '{column}' column."
                    )
                }), 400

        df = df.dropna(
            subset=["question", "reference_answer"]
        )

        if len(df) < 2:
            return jsonify({
                "error": "Dataset needs at least two valid rows."
            }), 400

        df["question"] = df["question"].astype(str)
        df["reference_answer"] = df["reference_answer"].astype(str)

        model = request.form.get(
            "model",
            DEFAULT_MODEL
        )

        strategies = json.loads(
            request.form.get("strategies", "[]")
        )

        valid_strategies = [
            item for item in strategies
            if item in STRATEGIES
        ]

        if not valid_strategies:
            return jsonify({
                "error": "Select at least one valid strategy."
            }), 400

        _, evaluation_df = train_test_split(
            df,
            test_size=0.30,
            random_state=42,
            shuffle=True
        )

        details = []

        totals = {
            strategy: {
                "accuracy": 0,
                "relevance": 0,
                "completeness": 0,
                "clarity": 0,
                "overall": 0,
                "count": 0
            }
            for strategy in valid_strategies
        }

        for _, row in evaluation_df.iterrows():

            question = row["question"]
            reference_answer = row["reference_answer"]

            row_results = []

            for strategy in valid_strategies:

                result = run_strategy(
                    question,
                    reference_answer,
                    strategy,
                    model
                )

                row_results.append(result)

                for metric in [
                    "accuracy",
                    "relevance",
                    "completeness",
                    "clarity",
                    "overall"
                ]:

                    totals[strategy][metric] += (
                        result["scores"][metric]
                    )

                totals[strategy]["count"] += 1

            details.append({
                "question": question,
                "reference_answer": reference_answer,
                "results": row_results
            })

        ranking = []

        for strategy in valid_strategies:

            count = totals[strategy]["count"]

            if count == 0:
                continue

            item = {
                "strategy": strategy
            }

            for metric in [
                "accuracy",
                "relevance",
                "completeness",
                "clarity",
                "overall"
            ]:

                item[metric] = round(
                    totals[strategy][metric] / count,
                    2
                )

            item["average_score"] = item["overall"]

            ranking.append(item)

        ranking.sort(
            key=lambda x: x["overall"],
            reverse=True
        )

        return jsonify({
            "success": True,
            "ranking": ranking,
            "details": details,
            "evaluation_rows": len(evaluation_df),
            "total_rows": len(df),
            "note": "Scores are AI-judge estimates."
        })

    except Exception as e:

        logger.exception("Dataset evaluation failed")

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# --------------------------------------------------
# HEALTH CHECK
# --------------------------------------------------

@app.route("/api/health", methods=["GET"])
def health():

    try:

        response = requests.get(
            f"{OLLAMA_URL}/api/tags",
            timeout=5
        )

        response.raise_for_status()

        return jsonify({
            "success": True,
            "flask": "running",
            "ollama": "connected"
        })

    except Exception as e:

        return jsonify({
            "success": False,
            "flask": "running",
            "ollama": "disconnected",
            "error": str(e)
        }), 503


# --------------------------------------------------
# START APPLICATION
# --------------------------------------------------

if __name__ == "__main__":

    print("\n====================================")
    print(" PROMPT QUALITY COMPARISON ASSISTANT")
    print("====================================")
    print("Model:", DEFAULT_MODEL)
    print("Ollama:", OLLAMA_URL)
    print("URL: http://127.0.0.1:5000")
    print("====================================\n")

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True
    )
