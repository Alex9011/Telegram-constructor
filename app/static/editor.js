const state = {
    blocks: [],
};

const blockContainer = document.getElementById("blockContainer");
const statusBox = document.getElementById("editorStatus");
const saveButton = document.getElementById("saveSchemeBtn");

const TYPE_PREFIX = {
    start: "start",
    message: "msg",
    buttons: "btn",
    input: "inp",
    end: "end",
};

function escapeHtml(value) {
    return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/\"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function setStatus(message, type = "info") {
    statusBox.className = `alert alert-${type}`;
    statusBox.textContent = message;
    statusBox.classList.remove("d-none");
}

function hideStatus() {
    statusBox.classList.add("d-none");
}

function ensureBlockShape(block) {
    const normalized = {
        uid: block.uid,
        type: block.type,
        data: block.data || {},
    };

    if (normalized.type === "buttons") {
        if (!Array.isArray(normalized.data.buttons)) {
            normalized.data.buttons = [];
        }
    }

    return normalized;
}

function blockExists(uid) {
    return state.blocks.some((block) => block.uid === uid);
}

function generateBlockId(type) {
    if (type === "start") {
        return "start";
    }

    const prefix = TYPE_PREFIX[type] || "b";
    let index = 1;
    let candidate = `${prefix}_${index}`;

    while (blockExists(candidate)) {
        index += 1;
        candidate = `${prefix}_${index}`;
    }

    return candidate;
}

function getDefaultData(type) {
    if (type === "start") {
        return { next_block_id: null };
    }

    if (type === "message") {
        return { text: "", next_block_id: null };
    }

    if (type === "buttons") {
        return {
            text: "",
            buttons: [
                { label: "Кнопка 1", next_block_id: null },
                { label: "Кнопка 2", next_block_id: null },
            ],
        };
    }

    if (type === "input") {
        return {
            question: "",
            variable_name: "user_input",
            next_block_id: null,
        };
    }

    return {};
}

function getBlockOptions(currentUid, selectedValue) {
    const items = ['<option value="">-- завершити --</option>'];

    for (const block of state.blocks) {
        if (block.uid === currentUid) {
            continue;
        }

        const selected = block.uid === selectedValue ? "selected" : "";
        items.push(
            `<option value="${escapeHtml(block.uid)}" ${selected}>${escapeHtml(block.uid)} (${escapeHtml(block.type)})</option>`
        );
    }

    return items.join("");
}

function renderNextSelect(currentUid, value, className, extraAttrs = "") {
    return `
        <select class="form-select ${className}" data-uid="${escapeHtml(currentUid)}" ${extraAttrs}>
            ${getBlockOptions(currentUid, value || "")}
        </select>
    `;
}

function renderButtonsEditor(block) {
    const buttons = Array.isArray(block.data.buttons) ? block.data.buttons : [];

    const rows = buttons
        .map((button, index) => {
            const label = button && button.label ? button.label : "";
            const nextBlockId = button && button.next_block_id ? button.next_block_id : "";

            return `
                <div class="row g-2 align-items-center mb-2">
                    <div class="col-12 col-md-4">
                        <input
                            type="text"
                            class="form-control js-btn-label"
                            data-uid="${escapeHtml(block.uid)}"
                            data-index="${index}"
                            value="${escapeHtml(label)}"
                            placeholder="Текст кнопки"
                        >
                    </div>
                    <div class="col-12 col-md-6">
                        ${renderNextSelect(block.uid, nextBlockId, "js-btn-next", `data-index="${index}"`)}
                    </div>
                    <div class="col-12 col-md-2 text-md-end">
                        <button
                            type="button"
                            class="btn btn-sm btn-outline-danger js-remove-btn"
                            data-uid="${escapeHtml(block.uid)}"
                            data-index="${index}"
                        >
                            Видалити
                        </button>
                    </div>
                </div>
            `;
        })
        .join("");

    const disableAdd = buttons.length >= 3 ? "disabled" : "";

    return `
        <div class="mb-2">
            <label class="form-label">Текст повідомлення</label>
            <textarea class="form-control js-buttons-text" data-uid="${escapeHtml(block.uid)}" rows="2">${escapeHtml(block.data.text || "")}</textarea>
        </div>
        <div class="mb-2">
            ${rows || '<div class="small text-secondary">Кнопок поки немає.</div>'}
            <button type="button" class="btn btn-sm btn-outline-primary js-add-btn" data-uid="${escapeHtml(block.uid)}" ${disableAdd}>
                Додати кнопку
            </button>
        </div>
    `;
}

function renderBlockFields(block) {
    if (block.type === "start") {
        return `
            <div class="mb-2">
                <label class="form-label">Next block</label>
                ${renderNextSelect(block.uid, block.data.next_block_id, "js-next")}
            </div>
        `;
    }

    if (block.type === "message") {
        return `
            <div class="mb-2">
                <label class="form-label">Text</label>
                <textarea class="form-control js-message-text" data-uid="${escapeHtml(block.uid)}" rows="2">${escapeHtml(block.data.text || "")}</textarea>
            </div>
            <div class="mb-2">
                <label class="form-label">Next block</label>
                ${renderNextSelect(block.uid, block.data.next_block_id, "js-next")}
            </div>
        `;
    }

    if (block.type === "buttons") {
        return renderButtonsEditor(block);
    }

    if (block.type === "input") {
        return `
            <div class="mb-2">
                <label class="form-label">Питання</label>
                <input type="text" class="form-control js-input-question" data-uid="${escapeHtml(block.uid)}" value="${escapeHtml(block.data.question || "")}">
            </div>
            <div class="mb-2">
                <label class="form-label">Назва змінної</label>
                <input type="text" class="form-control js-input-variable" data-uid="${escapeHtml(block.uid)}" value="${escapeHtml(block.data.variable_name || "")}">
            </div>
            <div class="mb-2">
                <label class="form-label">Next block</label>
                ${renderNextSelect(block.uid, block.data.next_block_id, "js-next")}
            </div>
        `;
    }

    return '<div class="small text-secondary">Кінцевий блок. Переходів немає.</div>';
}

function renderBlockCard(block) {
    return `
        <div class="card block-card border-0 shadow-sm">
            <div class="card-header d-flex justify-content-between align-items-center gap-2">
                <div>
                    <div class="fw-semibold mb-1">ID блоку</div>
                    <input
                        type="text"
                        class="form-control form-control-sm js-block-uid"
                        data-uid="${escapeHtml(block.uid)}"
                        value="${escapeHtml(block.uid)}"
                    >
                    <span class="badge text-bg-light block-type-badge">${escapeHtml(block.type)}</span>
                </div>
                <button type="button" class="btn btn-sm btn-outline-danger js-remove-block" data-uid="${escapeHtml(block.uid)}">
                    Видалити блок
                </button>
            </div>
            <div class="card-body">
                ${renderBlockFields(block)}
            </div>
        </div>
    `;
}

function refreshAddButtons() {
    const hasStart = state.blocks.some((block) => block.type === "start");
    const startButtons = document.querySelectorAll('.js-add-block[data-type="start"]');

    startButtons.forEach((button) => {
        button.disabled = hasStart;
    });
}

function renderBlocks() {
    if (!state.blocks.length) {
        blockContainer.innerHTML = '<div class="alert alert-warning">Немає блоків. Додайте блок start.</div>';
        refreshAddButtons();
        return;
    }

    blockContainer.innerHTML = state.blocks.map(renderBlockCard).join("");
    refreshAddButtons();
}

function findBlock(uid) {
    return state.blocks.find((block) => block.uid === uid);
}

function updateBlock(uid, mutator) {
    const block = findBlock(uid);
    if (!block) {
        return;
    }
    mutator(block);
}

function renameBlockUid(oldUid, nextUidRaw) {
    const nextUid = String(nextUidRaw || "").trim();
    if (!nextUid) {
        setStatus("ID блоку не може бути порожнім.", "warning");
        renderBlocks();
        return;
    }

    if (oldUid === nextUid) {
        renderBlocks();
        return;
    }

    const hasConflict = state.blocks.some(
        (block) => block.uid === nextUid && block.uid !== oldUid
    );
    if (hasConflict) {
        setStatus("Блок з таким ID вже існує.", "warning");
        renderBlocks();
        return;
    }

    const targetBlock = findBlock(oldUid);
    if (!targetBlock) {
        return;
    }

    targetBlock.uid = nextUid;

    // Keep all transition references valid after UID rename.
    for (const block of state.blocks) {
        if (block.data && block.data.next_block_id === oldUid) {
            block.data.next_block_id = nextUid;
        }

        if (Array.isArray(block.data.buttons)) {
            for (const button of block.data.buttons) {
                if (button.next_block_id === oldUid) {
                    button.next_block_id = nextUid;
                }
            }
        }
    }

    setStatus("ID блоку оновлено. Не забудьте зберегти схему.", "info");
    renderBlocks();
}

function clearReferencesToBlock(removedUid) {
    // Keep existing links valid after block deletion.
    for (const block of state.blocks) {
        if (block.data && block.data.next_block_id === removedUid) {
            block.data.next_block_id = null;
        }

        if (Array.isArray(block.data.buttons)) {
            for (const button of block.data.buttons) {
                if (button.next_block_id === removedUid) {
                    button.next_block_id = null;
                }
            }
        }
    }
}

function addBlock(type) {
    if (type === "start" && state.blocks.some((block) => block.type === "start")) {
        setStatus("Блок start вже існує.", "warning");
        return;
    }

    const uid = generateBlockId(type);
    state.blocks.push({
        uid,
        type,
        data: getDefaultData(type),
    });

    hideStatus();
    renderBlocks();
}

function removeBlock(uid) {
    state.blocks = state.blocks.filter((block) => block.uid !== uid);
    clearReferencesToBlock(uid);
    renderBlocks();
}

function addButtonToBlock(uid) {
    updateBlock(uid, (block) => {
        if (!Array.isArray(block.data.buttons)) {
            block.data.buttons = [];
        }

        if (block.data.buttons.length >= 3) {
            return;
        }

        block.data.buttons.push({
            label: `Кнопка ${block.data.buttons.length + 1}`,
            next_block_id: null,
        });
    });
    renderBlocks();
}

function removeButtonFromBlock(uid, index) {
    updateBlock(uid, (block) => {
        if (!Array.isArray(block.data.buttons)) {
            return;
        }
        block.data.buttons.splice(index, 1);
    });
    renderBlocks();
}

function extractErrorMessage(payload) {
    const detail = payload && payload.detail;

    if (Array.isArray(detail)) {
        return detail.join("\n");
    }

    if (typeof detail === "string") {
        return detail;
    }

    return "Помилка збереження схеми";
}

async function loadScheme() {
    try {
        const response = await fetch(`/api/projects/${PROJECT_ID}/scheme`);
        const payload = await response.json();

        if (!response.ok) {
            setStatus(extractErrorMessage(payload), "danger");
            return;
        }

        state.blocks = (payload.blocks || []).map(ensureBlockShape);
        hideStatus();
        renderBlocks();
    } catch (error) {
        setStatus("Не вдалося завантажити схему. Перевірте сервер.", "danger");
    }
}

async function saveScheme() {
    const requestBody = {
        blocks: state.blocks.map((block) => ({
            uid: block.uid,
            type: block.type,
            data: block.data,
        })),
    };

    try {
        const response = await fetch(`/api/projects/${PROJECT_ID}/scheme`, {
            method: "PUT",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify(requestBody),
        });

        const payload = await response.json();

        if (!response.ok) {
            setStatus(extractErrorMessage(payload), "danger");
            return;
        }

        state.blocks = (payload.scheme.blocks || []).map(ensureBlockShape);
        renderBlocks();
        setStatus("Схему успішно збережено.", "success");
    } catch (error) {
        setStatus("Не вдалося зберегти схему. Перевірте сервер.", "danger");
    }
}

document.querySelectorAll(".js-add-block").forEach((button) => {
    button.addEventListener("click", () => {
        addBlock(button.dataset.type);
    });
});

saveButton.addEventListener("click", saveScheme);

blockContainer.addEventListener("click", (event) => {
    const removeBlockButton = event.target.closest(".js-remove-block");
    if (removeBlockButton) {
        removeBlock(removeBlockButton.dataset.uid);
        return;
    }

    const addButton = event.target.closest(".js-add-btn");
    if (addButton) {
        addButtonToBlock(addButton.dataset.uid);
        return;
    }

    const removeButton = event.target.closest(".js-remove-btn");
    if (removeButton) {
        const uid = removeButton.dataset.uid;
        const index = Number(removeButton.dataset.index);
        removeButtonFromBlock(uid, index);
    }
});

blockContainer.addEventListener("input", (event) => {
    const target = event.target;
    const uid = target.dataset.uid;
    if (!uid) {
        return;
    }

    if (target.classList.contains("js-message-text")) {
        updateBlock(uid, (block) => {
            block.data.text = target.value;
        });
        return;
    }

    if (target.classList.contains("js-buttons-text")) {
        updateBlock(uid, (block) => {
            block.data.text = target.value;
        });
        return;
    }

    if (target.classList.contains("js-input-question")) {
        updateBlock(uid, (block) => {
            block.data.question = target.value;
        });
        return;
    }

    if (target.classList.contains("js-input-variable")) {
        updateBlock(uid, (block) => {
            block.data.variable_name = target.value;
        });
        return;
    }

    if (target.classList.contains("js-btn-label")) {
        const index = Number(target.dataset.index);
        updateBlock(uid, (block) => {
            if (!Array.isArray(block.data.buttons) || !block.data.buttons[index]) {
                return;
            }
            block.data.buttons[index].label = target.value;
        });
    }
});

blockContainer.addEventListener("change", (event) => {
    const target = event.target;
    const uid = target.dataset.uid;
    if (!uid) {
        return;
    }

    if (target.classList.contains("js-block-uid")) {
        renameBlockUid(uid, target.value);
        return;
    }

    if (target.classList.contains("js-next")) {
        updateBlock(uid, (block) => {
            block.data.next_block_id = target.value || null;
        });
        return;
    }

    if (target.classList.contains("js-btn-next")) {
        const index = Number(target.dataset.index);
        updateBlock(uid, (block) => {
            if (!Array.isArray(block.data.buttons) || !block.data.buttons[index]) {
                return;
            }
            block.data.buttons[index].next_block_id = target.value || null;
        });
    }
});

loadScheme();
