const keyField = document.querySelector('#key');
const notice = document.querySelector('#notice');
const status = document.querySelector('#status');
const connection = document.querySelector('#connection');
const coach = document.querySelector('#coach');
const moves = document.querySelector('#moves');
const arrows = document.querySelector('#arrows');

function showPreferences(values) {
    coach.checked = values.coachEnabled;
    moves.value = String(values.coachMoves);
    moves.disabled = !coach.checked;
    arrows.checked = values.showArrows;
}

chrome.storage.local.get({key: '', coachEnabled: false, coachMoves: 3, showArrows: true}).then(values => {
    keyField.value = values.key;
    connection.open = !values.key;
    showPreferences(values);
});
chrome.storage.onChanged.addListener((changes, area) => {
    if (area === 'local' && changes.coachEnabled) {
        coach.checked = changes.coachEnabled.newValue;
        moves.disabled = !coach.checked;
    }
});
coach.onchange = () => {
    moves.disabled = !coach.checked;
    chrome.storage.local.set({coachEnabled: coach.checked});
};
moves.onchange = () => chrome.storage.local.set({coachMoves: Number(moves.value)});
arrows.onchange = () => chrome.storage.local.set({showArrows: arrows.checked});

async function refresh(type = 'status') {
    try {
        const state = await chrome.runtime.sendMessage({type});
        status.textContent = state.message;
        status.dataset.state = state.state;
        if (state.state === 'repair') connection.open = true;
    } catch {
        status.textContent = 'Reload Browser Reader from Extensions, then reload the chess tab.';
        status.dataset.state = 'disconnected';
    }
}
document.querySelector('#pairing').onsubmit = async event => {
    event.preventDefault();
    await chrome.storage.local.set({key: keyField.value.trim()});
    await refresh('reconnect');
};
document.querySelector('#copy').onclick = async () => {
    if (!keyField.value.trim()) {
        notice.textContent = 'Enter a key first.';
        return;
    }
    try {
        await navigator.clipboard.writeText(keyField.value.trim());
        notice.textContent = 'Key copied.';
    } catch {
        keyField.select();
        notice.textContent = 'Key selected. Press Copy.';
    }
};
refresh();
setInterval(refresh, 1000);
