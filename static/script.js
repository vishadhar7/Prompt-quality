
document.addEventListener("DOMContentLoaded", () => {

    const manualMode = document.getElementById("manualMode");
    const datasetMode = document.getElementById("datasetMode");

    const manualSection = document.getElementById("manualSection");
    const datasetSection = document.getElementById("datasetSection");

    const questionInput = document.getElementById("question");
    const referenceInput = document.getElementById("reference");
    const datasetFile = document.getElementById("datasetFile");

    const modelSelect = document.getElementById("model");
    const compareButton = document.getElementById("compare");

    const loading = document.getElementById("loading");
    const error = document.getElementById("error");
    const errorMessage = document.getElementById("errorMessage");

    const results = document.getElementById("results");

    const status = document.getElementById("status");
    const statusDot = document.getElementById("statusDot");

    const winner = document.getElementById("winner");
    const scoreTableBody = document.getElementById("scoreTableBody");
    const answerCards = document.getElementById("answerCards");

    const rankingBody = document.getElementById("rankingBody");
    const datasetDetails = document.getElementById("datasetDetails");

    const manualResults = document.getElementById("manualResults");
    const datasetResults = document.getElementById("datasetResults");

    const resultNote = document.getElementById("resultNote");

    let currentMode = "manual";


    // ----------------------------------
    // MODE SWITCHING
    // ----------------------------------

    function setMode(mode) {

        currentMode = mode;

        manualSection.classList.toggle("hidden", mode !== "manual");
        datasetSection.classList.toggle("hidden", mode !== "dataset");

        manualMode.classList.toggle("active", mode === "manual");
        datasetMode.classList.toggle("active", mode === "dataset");

        hideError();
        hideResults();
    }

    manualMode.addEventListener("click", () => setMode("manual"));
    datasetMode.addEventListener("click", () => setMode("dataset"));


    // ----------------------------------
    // ERROR AND LOADING
    // ----------------------------------

    function showError(message) {
        errorMessage.textContent = message;
        error.classList.remove("hidden");
    }

    function hideError() {
        error.classList.add("hidden");
        errorMessage.textContent = "";
    }

    function showLoading() {
        loading.classList.remove("hidden");
        compareButton.disabled = true;
        compareButton.textContent = "Processing...";
    }

    function hideLoading() {
        loading.classList.add("hidden");
        compareButton.disabled = false;
        compareButton.textContent = "Generate and Compare";
    }

    function hideResults() {
        results.classList.add("hidden");
    }

    function showResults() {
        results.classList.remove("hidden");
    }


    // ----------------------------------
    // SAFE TEXT AND SCORES
    // ----------------------------------

    function escapeHTML(value) {

        return String(value ?? "").replace(/[&<>"']/g, character => ({
            "&": "&amp;",
            "<": "&lt;",
            ">": "&gt;",
            '"': "&quot;",
            "'": "&#039;"
        })[character]);

    }

    function formatScore(value) {

        const score = Number(value);

        return Number.isFinite(score) ? score.toFixed(2) : "0.00";

    }


    // ----------------------------------
    // LOAD OLLAMA MODELS
    // ----------------------------------

    async function refreshModels() {

        try {

            const response = await fetch("/api/models");
            const data = await response.json();

            if (!response.ok || !data.success) {
                throw new Error(data.error || "Ollama connection failed.");
            }

            modelSelect.innerHTML = "";

            data.models.forEach(model => {

                const option = document.createElement("option");
                option.value = model;
                option.textContent = model;

                modelSelect.appendChild(option);

            });

            status.textContent = "Connected to Ollama";
            statusDot.classList.add("connected");
            statusDot.classList.remove("disconnected");

        } catch (err) {

            status.textContent = "Ollama disconnected";
            statusDot.classList.add("disconnected");
            statusDot.classList.remove("connected");

            console.error(err);

        }

    }


    // ----------------------------------
    // SELECTED STRATEGIES
    // ----------------------------------

    function getSelectedStrategies() {

        return Array.from(
            document.querySelectorAll('input[name="strategy"]:checked')
        ).map(item => item.value);

    }


    // ----------------------------------
    // READ API RESPONSE
    // ----------------------------------

    async function readResponse(response) {

        const text = await response.text();

        let data;

        try {
            data = JSON.parse(text);
        } catch (err) {
            console.error("Invalid server response:", text);
            throw new Error("Invalid response from Flask. Check terminal.");
        }

        if (!response.ok) {
            throw new Error(data.error || `HTTP error ${response.status}`);
        }

        return data;

    }


    // ----------------------------------
    // MANUAL API REQUEST
    // ----------------------------------

    async function runManualComparison(strategies, model) {

        const question = questionInput.value.trim();
        const reference = referenceInput.value.trim();

        if (!question) {
            throw new Error("Please enter a question.");
        }

        if (!reference) {
            throw new Error("Please enter a reference answer.");
        }

        const response = await fetch("/api/compare", {

            method: "POST",

            headers: {
                "Content-Type": "application/json"
            },

            body: JSON.stringify({
                question: question,
                reference_answer: reference,
                model: model,
                strategies: strategies
            })

        });

        return await readResponse(response);

    }


    // ----------------------------------
    // DATASET API REQUEST
    // ----------------------------------

    async function runDatasetComparison(strategies, model) {

        const file = datasetFile.files[0];

        if (!file) {
            throw new Error("Please select a CSV file.");
        }

        const formData = new FormData();

        formData.append("file", file);
        formData.append("model", model);
        formData.append("strategies", JSON.stringify(strategies));

        const response = await fetch("/api/evaluate_dataset", {

            method: "POST",
            body: formData

        });

        return await readResponse(response);

    }


    // ----------------------------------
    // MANUAL RESULTS
    // ----------------------------------

    function displayManualResults(data) {

        const list = data.results || [];

        if (!list.length) {
            throw new Error("No results returned.");
        }

        manualResults.classList.remove("hidden");
        datasetResults.classList.add("hidden");

        const sorted = [...list].sort(
            (a, b) => Number(b.scores?.overall || 0) -
                      Number(a.scores?.overall || 0)
        );

        const best = sorted[0];

        winner.innerHTML = `
            <h3>Best Performing Strategy</h3>
            <h2>${escapeHTML(best.strategy)}</h2>
            <p>Overall Score: ${formatScore(best.scores?.overall)} / 10</p>
        `;

        scoreTableBody.innerHTML = "";

        list.forEach(item => {

            const score = item.scores || {};
            const row = document.createElement("tr");

            row.innerHTML = `
                <td>${escapeHTML(item.strategy)}</td>
                <td>${formatScore(score.accuracy)}</td>
                <td>${formatScore(score.relevance)}</td>
                <td>${formatScore(score.completeness)}</td>
                <td>${formatScore(score.clarity)}</td>
                <td><strong>${formatScore(score.overall)}</strong></td>
            `;

            scoreTableBody.appendChild(row);

        });

        answerCards.innerHTML = "";

        list.forEach(item => {

            const card = document.createElement("div");
            card.className = "answer-card";

            card.innerHTML = `
                <h3>${escapeHTML(item.strategy)}</h3>

                <p class="evaluation-status">
                    ${item.evaluation_valid
                        ? "Evaluation completed"
                        : "Evaluation unavailable"}
                </p>

                <div class="answer-content">
                    ${escapeHTML(item.answer).replace(/\n/g, "<br>")}
                </div>

                <h4>Evaluation Scores</h4>

                <p>Accuracy: ${formatScore(item.scores?.accuracy)} / 10</p>
                <p>Relevance: ${formatScore(item.scores?.relevance)} / 10</p>
                <p>Completeness: ${formatScore(item.scores?.completeness)} / 10</p>
                <p>Clarity: ${formatScore(item.scores?.clarity)} / 10</p>
                <p>Overall: ${formatScore(item.scores?.overall)} / 10</p>

                <h4>Feedback</h4>
                <p>${escapeHTML(item.feedback)}</p>
            `;

            answerCards.appendChild(card);

        });

        resultNote.textContent = data.note || "";

    }


    // ----------------------------------
    // DATASET RESULTS
    // ----------------------------------

    function displayDatasetResults(data) {

        const ranking = data.ranking || [];
        const details = data.details || [];

        if (!ranking.length) {
            throw new Error("No dataset ranking returned.");
        }

        manualResults.classList.add("hidden");
        datasetResults.classList.remove("hidden");

        rankingBody.innerHTML = "";

        ranking.forEach((item, index) => {

            const row = document.createElement("tr");

            row.innerHTML = `
                <td>${index + 1}</td>
                <td>${escapeHTML(item.strategy)}</td>
                <td>${formatScore(item.accuracy)}</td>
                <td>${formatScore(item.relevance)}</td>
                <td>${formatScore(item.completeness)}</td>
                <td>${formatScore(item.clarity)}</td>
                <td><strong>${formatScore(item.overall)}</strong></td>
            `;

            rankingBody.appendChild(row);

        });

        datasetDetails.innerHTML = "";

        details.forEach((item, index) => {

            const card = document.createElement("div");
            card.className = "dataset-detail-card";

            let strategyHTML = "";

            (item.results || []).forEach(result => {

                strategyHTML += `
                    <div class="strategy-result">

                        <h4>${escapeHTML(result.strategy)}</h4>

                        <p>
                            Overall:
                            ${formatScore(result.scores?.overall)} / 10
                        </p>

                        <p>
                            ${result.evaluation_valid
                                ? "Evaluation completed"
                                : "Evaluation unavailable"}
                        </p>

                        <p>${escapeHTML(result.feedback)}</p>

                    </div>
                `;

            });

            card.innerHTML = `
                <h3>Question ${index + 1}</h3>

                <p>
                    <strong>Question:</strong>
                    ${escapeHTML(item.question)}
                </p>

                <p>
                    <strong>Reference:</strong>
                    ${escapeHTML(item.reference_answer)}
                </p>

                ${strategyHTML}
            `;

            datasetDetails.appendChild(card);

        });

        resultNote.textContent =
            `${data.evaluation_rows} questions evaluated. ${data.note || ""}`;

    }


    // ----------------------------------
    // DISPLAY RESULTS
    // ----------------------------------

    function displayResults(data) {

        if (!data || data.success !== true) {
            throw new Error(data?.error || "Invalid response.");
        }

        if (currentMode === "manual") {
            displayManualResults(data);
        } else {
            displayDatasetResults(data);
        }

        showResults();

    }


    // ----------------------------------
    // COMPARE BUTTON
    // ----------------------------------

    compareButton.addEventListener("click", async () => {

        hideError();
        hideResults();

        const strategies = getSelectedStrategies();
        const model = modelSelect.value;

        if (!strategies.length) {
            showError("Please select at least one strategy.");
            return;
        }

        if (!model) {
            showError("Please select an Ollama model.");
            return;
        }

        showLoading();

        try {

            let data;

            if (currentMode === "manual") {

                data = await runManualComparison(strategies, model);

            } else {

                data = await runDatasetComparison(strategies, model);

            }

            displayResults(data);

        } catch (err) {

            console.error("Comparison failed:", err);
            showError(err.message || "Something went wrong.");

        } finally {

            hideLoading();

        }

    });


    // ----------------------------------
    // INITIALIZE
    // ----------------------------------

    setMode("manual");
    refreshModels();

});
