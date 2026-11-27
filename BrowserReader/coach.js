const boardLensCoach = (() => {
    const defaults = {coachEnabled: false, coachMoves: 3, showArrows: true};
    let settings = {...defaults};
    let snapshot = null;
    let boardVisible = false;
    let hadHint = false;
    let signature = '';
    let host, body;

    function element(tag, text, className) {
        const node = document.createElement(tag);
        if (text) node.textContent = text;
        if (className) node.className = className;
        return node;
    }

    function mount() {
        host = element('div');
        host.dataset.boardlens = 'coach';
        const shadow = host.attachShadow({mode: 'open'});
        const style = element('style', `
            :host { all: initial; position: fixed; right: 14px; bottom: 14px; z-index: 2147483647;
                width: min(306px, calc(100vw - 28px)); color-scheme: dark; }
            :host([hidden]) { display: none; }
            section { box-sizing: border-box; border: 1px solid #624782; border-radius: 14px;
                padding: 12px 14px; background: #20172e; color: #f4ebff;
                box-shadow: 0 5px 20px #0007; max-height: min(510px, 55vh);
                overflow: auto; font: 14px/1.45 system-ui; overflow-wrap: anywhere; }
            header { display: flex; align-items: center; justify-content: space-between;
                gap: 10px; color: #dac5ff; }
            button { border: 1px solid #654c85; border-radius: 7px; color: #f4ebff;
                background: #39294d; font: inherit; min-height: 32px; padding: 3px 9px; cursor: pointer; }
            h2 { font-size: 15px; margin: 0; } h3 { font-size: 14px; margin: 0; }
            p { margin: 6px 0 0; } .muted { color: #c9badd; font-size: 12px; }
            article { border-top: 1px solid #4a385f; padding-top: 8px; margin-top: 10px; }
        `);
        const panel = element('section');
        const header = element('header');
        const title = element('h2', 'BoardLens Coach');
        title.id = 'title';
        panel.setAttribute('aria-labelledby', title.id);
        const close = element('button', 'Hide');
        close.addEventListener('click', () => {
            settings.coachEnabled = false;
            render();
            chrome.storage.local.set({coachEnabled: false});
        });
        header.append(title, close);
        body = element('div');
        panel.append(header, body);
        shadow.append(style, panel);
        document.documentElement.append(host);
    }

    function render() {
        if (!settings.coachEnabled || !boardVisible) {
            if (host) host.hidden = true;
            signature = '';
            return;
        }
        if (!host) mount();
        host.hidden = false;
        const currentSignature = JSON.stringify([snapshot, hadHint, settings.coachMoves]);
        if (signature === currentSignature) return;
        signature = currentSignature;
        body.replaceChildren();
        if (!snapshot) {
            body.append(element('p', hadHint ? 'Update BoardLens desktop to use Coach mode.' :
                'Waiting for analysis of this position.', 'muted'));
            return;
        }
        body.append(element('p', [snapshot.side + ' to move', snapshot.engine].filter(Boolean).join(' · '), 'muted'));
        if (snapshot.score && snapshot.score !== '—') {
            body.append(element('p', [snapshot.score, snapshot.evaluator].filter(Boolean).join(' · ')));
        }
        const moves = snapshot.moves.slice(0, settings.coachMoves);
        if (!moves.length) {
            body.append(element('p', snapshot.waiting_for_turn ? 'Waiting for your side to move.' :
                'Use Suggest or Auto suggest in BoardLens for coaching here.', 'muted'));
        }
        for (const move of moves) {
            const card = element('article');
            const score = move.score && move.score !== '—' ? ' · ' + move.score : '';
            card.append(element('h3', move.san + score));
            if (move.description) card.append(element('p', move.description));
            if (move.insights) card.append(element('p', move.insights, 'muted'));
            if (move.reply_simple) card.append(element('p', 'Likely reply ' + move.reply_simple, 'muted'));
            body.append(card);
        }
    }

    chrome.storage.local.get(defaults).then(saved => {
        settings = {...defaults, ...saved};
        render();
    }).catch(() => {});
    chrome.storage.onChanged.addListener((changes, area) => {
        if (area !== 'local') return;
        for (const key of Object.keys(defaults)) {
            if (key in changes) settings[key] = changes[key].newValue ?? defaults[key];
        }
        render();
    });

    return {
        get showArrows() { return settings.showArrows; },
        get candidateCount() { return settings.coachEnabled ? Number(settings.coachMoves) : null; },
        update(coach, hasHint = false) {
            snapshot = coach || null;
            hadHint = hasHint;
            boardVisible = true;
            render();
        },
        clear() {
            snapshot = null;
            boardVisible = false;
            render();
        }
    };
})();
