// Run with Playwright and a Chromium executable on a graphical desktop:
// CHROME_PATH=/path/to/chrome node desktop/tests/browser_lookahead.cjs
const assert = require('node:assert/strict');
const {spawn} = require('node:child_process');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const {once} = require('node:events');
const {chromium} = require('playwright');

const extension = process.env.BROWSER_READER_PATH || path.resolve(__dirname, '../../BrowserReader');
const fen = 'rn1q4/ppp2kpp/1b2bn2/4P3/8/6Q1/PPP2PPP/RNB1K2R b KQ - 4 12';
const nextFen = 'rn1q4/ppp2kpp/1b2b3/4P3/4n3/6Q1/PPP2PPP/RNB1K2R w KQ - 5 13';
const moves = ['f6e4', 'g3f4', 'f7g8', 'f4e4'];
const colors = ['#e0a12b', '#21b49a', '#dd67ab', '#6784df'];
const host = '[data-boardlens="overlay"]';
const root = host + ' [data-boardlens="arrows"]';
const wait = (page, fn, arg) => page.waitForFunction(fn, arg, {polling: 35, timeout: 8000});

async function startBrowser(profile) {
    const executable = process.env.CHROME_PATH || chromium.executablePath();
    const child = spawn(executable, ['--no-first-run', '--no-default-browser-check',
        '--disable-sync', '--disable-background-networking', '--remote-debugging-port=0',
        '--user-data-dir=' + profile, '--window-size=690,670', 'about:blank']);
    const closed = once(child, 'exit');
    try {
        const endpoint = await new Promise((resolve, reject) => {
            const timer = setTimeout(() => reject(Error('Chromium did not start')), 12000);
            child.once('error', error => { clearTimeout(timer); reject(error); });
            child.stderr.on('data', data => {
                const url = String(data).match(/DevTools listening on (ws:\/\/\S+)/);
                if (url) { clearTimeout(timer); resolve(url[1]); }
            });
        });
        // The normal Playwright launch path forces every tab to report it has focus.
        const browser = await chromium.connectOverCDP(endpoint, {noDefaults: true});
        return {browser, child, closed};
    } catch (error) {
        child.kill();
        throw error;
    }
}

async function run(browser) {
    const context = browser.contexts()[0];
    const protocol = await browser.newBrowserCDPSession();
    const board = context.pages()[0];
    const errors = [];
    board.on('pageerror', error => errors.push(error.message));
    const fixtureUrl = 'https://www.chess.com/play/computer/offline-fixture';
    await context.route('**/*', route => route.request().url() !== fixtureUrl ? route.abort() : route.fulfill({
        contentType: 'text/html',
        body: '<style>wc-chess-board{display:block;width:480px;height:480px}text{display:none!important;fill:transparent!important}</style><wc-chess-board></wc-chess-board>'
    }));
    await board.goto(fixtureUrl);
    await board.evaluate(({fen, moves, colors}) => {
        window.position = fen;
        document.querySelector('wc-chess-board').game = {
            getFEN: () => window.position, getOptions: () => ({flipped: true, id: 'play-computer'}),
            getVariant: () => 'chess', getMode: () => ({name: 'playing'}),
            isAtEndOfLine: () => true, isGameOver: () => false
        };
        window.focusReports = [];
        window.releaseCount = 0;
        window.renderedColors = [];
        window.emptyFrames = 0;
        Object.assign(window.chrome, {
            storage: {local: {get: (_, cb) => cb ? cb({}) : Promise.resolve({}), set() {}},
                      onChanged: {addListener() {}}},
            runtime: {onMessage: {addListener() {}}, async sendMessage(request) {
                if (request.type !== 'boards') return {};
                if (!request.visible) { window.releaseCount++; return {}; }
                const b = request.boards[0];
                if (!b) return {};
                if (window.omitHint) return {arrows_visible: window.showTestArrows};
                window.focusReports.push([request.focused, b.practice_focused]);
                if (window.pauseNext) {
                    window.pauseNext = false;
                    await new Promise(resolve => { window.finishReply = resolve; });
                    window.finishReply = null;
                    return {'browser:0': {fen: b.fen, board_id: b.board_id,
                        arrows: [{move: moves[0], color: '#ff0011', lookahead_ply: 1}]}};
                }
                const line = b.fen === fen ? moves : moves.slice(1);
                return {'browser:0': {fen: b.fen, board_id: b.board_id,
                    evaluation: {score: '+0.42'},
                    arrows: line.map((move, i) => ({move, color: colors[i], dashed: true, lookahead_ply: i + 1}))}};
            }}
        });
    }, {fen, moves, colors});
    for (const file of ['coach.js', 'content.js', 'reader.js']) {
        await board.addScriptTag({path: path.join(extension, file)});
    }
    const labels = () => board.locator(root + ' text').allTextContents();
    await wait(board, () => document.querySelector('[data-boardlens="overlay"]')?.shadowRoot.querySelectorAll('text').length === 4);
    await board.evaluate(selector => {
        const svg = document.querySelector(selector).shadowRoot.querySelector('svg');
        new MutationObserver(() => {
            if (!svg.querySelector('text')) window.emptyFrames++;
            for (const use of svg.querySelectorAll('use[color]')) window.renderedColors.push(use.getAttribute('color'));
        }).observe(svg, {childList: true});
    }, host);
    assert.deepEqual(await labels(), ['1', '2', '3', '4']);

    const geometry = await board.locator(root).evaluate(svg => {
        const rectangle = document.querySelector('wc-chess-board').getBoundingClientRect();
        const cell = rectangle.width / 8;
        return Array.from(svg.querySelectorAll('use[data-lookahead-ply]'), use => {
            const {lookaheadPly, move} = use.dataset;
            const number = svg.querySelector('text[data-lookahead-ply="' + lookaheadPly + '"]');
            const badge = number.parentElement.querySelector('rect');
            const [shaft, head] = svg.querySelector(use.getAttribute('href')).querySelectorAll('path');
            const length = shaft.getTotalLength();
            const tip = head.getPointAtLength(0);
            // On a flipped board h1 sits at the top left.
            const col = Math.floor((tip.x - rectangle.left) / cell);
            const row = Math.floor((tip.y - rectangle.top) / cell);
            const square = String.fromCharCode(104 - col) + String(row + 1);
            const x = Number(number.getAttribute('x')), y = Number(number.getAttribute('y'));
            let distance = Infinity;
            for (let step = 0; step <= length; step += .5) {
                const point = shaft.getPointAtLength(step);
                distance = Math.min(distance, Math.hypot(x - point.x, y - point.y));
            }
            return {move, labelMove: number.dataset.move, number: number.textContent, square,
                color: use.getAttribute('color'), tip: [tip.x / cell, tip.y / cell],
                distance, length: length / cell,
                visible: getComputedStyle(number).display !== 'none' && getComputedStyle(number).fill === 'rgb(255, 255, 255)',
                badgeCentered: Math.abs(Number(badge.getAttribute('x')) + Number(badge.getAttribute('width')) / 2 - x) < .05 &&
                    Math.abs(Number(badge.getAttribute('y')) + Number(badge.getAttribute('height')) / 2 - y) < .05};
        });
    });
    assert.deepEqual(geometry.map(g => g.move), moves);
    assert.deepEqual(geometry.map(g => g.color), colors);
    for (const [i, arrow] of geometry.entries()) {
        assert.equal(arrow.square, moves[i].slice(2), 'arrow landed outside its destination');
        assert.equal(arrow.labelMove, moves[i]);
        assert.ok(arrow.visible && arrow.badgeCentered, 'number and its background should be visible on the shaft');
        assert.equal(arrow.number, String(i + 1));
        assert.ok(arrow.distance <= .5, 'label drifted off arrow ' + arrow.number);
    }
    assert.equal(geometry[0].length, 3, 'knight arrow should follow two legs');
    const [first, fourth] = [geometry[0].tip, geometry[3].tip];
    assert.ok(Math.hypot(first[0] - fourth[0], first[1] - fourth[1]) >= .22, 'e4 arrowheads overlap');
    await board.evaluate(() => {
        window.omitHint = true;
        window.showTestArrows = true;
        document.querySelector('[data-boardlens="overlay"]').remove();
    });
    await board.locator(host).waitFor({state:'attached'});
    assert.deepEqual(await labels(), ['1', '2', '3', '4'], 'retained hints for the same visible FEN');
    await board.evaluate(() => {window.showTestArrows = false;});
    await wait(board, () => document.querySelector('[data-boardlens="overlay"]').shadowRoot.querySelectorAll('text').length === 0);
    await board.evaluate(() => {window.omitHint = false;});
    await wait(board, () => document.querySelector('[data-boardlens="overlay"]').shadowRoot.querySelectorAll('text').length === 4);
    if (process.env.BOARDLENS_LABELS_ONLY) return;

    const open = async newWindow => {
        const [page] = await Promise.all([context.waitForEvent('page'),
            protocol.send('Target.createTarget', {url: 'about:blank', newWindow})]);
        return page;
    };
    const otherTab = await open(false);
    await board.bringToFront();
    await wait(board, () => document.hasFocus() && document.visibilityState === 'visible');
    await wait(board, () => document.querySelector('[data-boardlens="overlay"]')?.shadowRoot.querySelectorAll('text').length === 4);
    await board.evaluate(() => { window.emptyFrames = 0; window.focusReports = []; });
    const otherWindow = await open(true);
    await otherWindow.bringToFront();
    await wait(board, () => !document.hasFocus() && document.visibilityState === 'visible');
    await wait(board, () => window.focusReports.some(([focus, practiceFocus]) => !focus && !practiceFocus));
    assert.deepEqual(await labels(), ['1', '2', '3', '4']);
    assert.equal(await board.evaluate(() => window.emptyFrames), 0, 'visible blur briefly cleared the prediction');
    assert.equal(await board.locator('[data-boardlens="evaluation"] strong').textContent(), '+0.42');

    // Hold an old response while the visible unfocused window changes position.
    await board.evaluate(() => { window.pauseNext = true; });
    await wait(board, () => !!window.finishReply);
    await board.evaluate(value => { window.position = value; }, nextFen);
    await wait(board, () => !document.querySelector('[data-boardlens="overlay"]')?.shadowRoot.querySelector('text'));
    await board.evaluate(() => window.finishReply());
    await wait(board, () => document.querySelector('[data-boardlens="overlay"]')?.shadowRoot.querySelectorAll('text').length === 3);

    // Hide, then restore the very same position before its obsolete response returns.
    await board.bringToFront();
    await board.evaluate(() => { window.releaseCount = 0; window.pauseNext = true; });
    await wait(board, () => !!window.finishReply);
    await otherTab.bringToFront();
    await wait(board, () => document.visibilityState === 'hidden' && window.releaseCount > 0);
    assert.deepEqual(await labels(), []);
    assert.equal(await board.locator('[data-boardlens="evaluation"]').count(), 0);
    await board.bringToFront();
    await wait(board, () => document.visibilityState === 'visible' && document.hasFocus());
    await board.evaluate(() => window.finishReply());
    await wait(board, () => document.querySelector('[data-boardlens="overlay"]')?.shadowRoot.querySelectorAll('text').length === 3);
    assert.equal(await board.evaluate(() => window.renderedColors.includes('#ff0011')), false);
    await board.evaluate(value => { window.position = value; }, fen);
    await wait(board, () => document.querySelector('[data-boardlens="overlay"]')?.shadowRoot.querySelectorAll('text').length === 4);
    assert.deepEqual(errors, []);

}

(async () => {
    const profile = await fs.mkdtemp(path.join(os.tmpdir(), 'boardlens-browser-test-'));
    let instance;
    try {
        instance = await startBrowser(profile);
        await run(instance.browser);
        console.log(process.env.BOARDLENS_LABELS_ONLY
            ? 'Verified four readable numbers on the flipped board shafts, with separate e4 arrowheads.'
            : 'Verified numbered paths, window blur, hidden tab release, and delayed replies.');
    } finally {
        if (instance) {
            const protocol = await instance.browser.newBrowserCDPSession();
            await protocol.send('Browser.close').catch(() => instance.child.kill());
            await instance.closed;
        }
        await fs.rm(profile, {recursive: true, force: true, maxRetries: 5, retryDelay: 100});
    }
})().catch(error => { console.error(error); process.exitCode = 1; });
