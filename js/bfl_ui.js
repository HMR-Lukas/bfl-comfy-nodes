import { app } from "../../scripts/app.js";

/*
 * Header pricing badges for the direct Black Forest Labs nodes.
 *
 * The nodes remain ordinary custom nodes. We intentionally do NOT set
 * nodeData.api_node, because that would make ComfyUI treat them as Partner/API
 * Nodes backed by Comfy infrastructure.
 *
 * Prices shown here are BFL credits (1 BFL credit = $0.01), not Comfy Credits.
 * If the BFL submit response returns an exact `cost`, the badge switches to the
 * exact charged value after execution.
 */


// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function widget(node, name, fallback = undefined) {
    const item = node.widgets?.find((w) => w.name === name);
    return item ? item.value : fallback;
}

function hasConnectedInput(node, name) {
    const slot = node.inputs?.find((input) => input.name === name);
    return slot?.link != null;
}

function anyConnectedInput(node, names) {
    return names.some((name) => hasConnectedInput(node, name));
}

function round1(value) {
    return Math.round(value * 10) / 10;
}

function formatNumber(value) {
    const rounded = round1(value);
    return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
}

function credits(value, prefix = "") {
    return `${prefix}${formatNumber(value)} BFL credits/Run`;
}

function creditsRange(min, max, prefix = "~") {
    return `${prefix}${formatNumber(min)}–${formatNumber(max)} BFL credits/Run`;
}

function actualOrEstimate(node, estimateFn) {
    if (Number.isFinite(node.__bflActualCost)) {
        return credits(node.__bflActualCost);
    }
    return estimateFn(node);
}


// ---------------------------------------------------------------------------
// FLUX 2 estimates
//
// Pro/Max formulas mirror ComfyUI's official BFL Partner Node pricing logic.
// When width/height are 0 (BFL auto sizing), only a minimum/range can be shown.
// ---------------------------------------------------------------------------

const FLUX2_IMAGE_INPUTS = [
    "input_image",
    "input_image_2",
    "input_image_3",
    "input_image_4",
    "input_image_5",
    "input_image_6",
    "input_image_7",
    "input_image_8",
];

function outputMegapixels(node) {
    const width = Number(widget(node, "width", 0));
    const height = Number(widget(node, "height", 0));

    if (!(width > 0 && height > 0)) {
        return null;
    }

    return Math.max(
        1,
        Math.ceil((width * height) / (1024 * 1024))
    );
}

function flux2ProPrice(node) {
    const mp = outputMegapixels(node);
    const hasRefs = anyConnectedInput(node, FLUX2_IMAGE_INPUTS);

    if (mp == null) {
        return hasRefs
            ? "~4.5–15+ BFL credits/Run"
            : "from 3 BFL credits/Run";
    }

    const outputCost = 3 + 1.5 * (mp - 1);

    if (hasRefs) {
        return creditsRange(outputCost + 1.5, outputCost + 12);
    }

    return credits(outputCost);
}

function flux2MaxPrice(node) {
    const mp = outputMegapixels(node);
    const hasRefs = anyConnectedInput(node, FLUX2_IMAGE_INPUTS);

    if (mp == null) {
        return hasRefs
            ? "~10–31+ BFL credits/Run"
            : "from 7 BFL credits/Run";
    }

    const outputCost = 7 + 3 * (mp - 1);

    if (hasRefs) {
        return creditsRange(outputCost + 3, outputCost + 24);
    }

    return credits(outputCost);
}

function flux2FlexPrice(node) {
    // BFL's central pricing page currently lists FLUX.2 [flex] from $0.05.
    // Other model overview pages have lagged behind this value, so do not
    // pretend we know the exact pre-run MP formula here. The submit response
    // replaces this with the exact charged `cost` after execution.
    return "from 5 BFL credits/Run";
}


// ---------------------------------------------------------------------------
// FLUX 3 estimates
// ---------------------------------------------------------------------------

const FLUX3_FULL_RATES = {
    t2v: { "720p": 17, "1080p": 29 },
    i2v: { "720p": 17, "1080p": 29 },
    v2v: { "720p": 43, "1080p": 54 },
};

const FLUX3_DRAFT_RATES = {
    t2v: 6,
    i2v: 6,
    v2v: 12,
};

function flux3Price(node, mode) {
    const duration = widget(node, "duration", "auto");
    const resolution = widget(node, "resolution", "720p");
    const draft = Boolean(widget(node, "draft", false));

    const rate = draft
        ? FLUX3_DRAFT_RATES[mode]
        : FLUX3_FULL_RATES[mode][resolution];

    if (duration === "auto") {
        return `${formatNumber(rate)} BFL credits/s`;
    }

    const seconds = Number(duration);

    if (!Number.isFinite(seconds)) {
        return `${formatNumber(rate)} BFL credits/s`;
    }

    return credits(rate * seconds);
}


function flux3LegacyPrice(node) {
    const selectedMode = widget(node, "mode", "t2v");
    const mode = selectedMode === "v2v" ? "v2v" : selectedMode === "i2v" ? "i2v" : "t2v";

    // The legacy node used hd/fhd labels. Normalize them for the shared table.
    const originalResolution = widget(node, "resolution", "hd");
    const normalizedResolution = originalResolution === "fhd" || originalResolution === "1080p"
        ? "1080p"
        : "720p";

    const duration = widget(node, "duration", "auto");
    const draft = Boolean(widget(node, "draft", false));
    const rate = draft
        ? FLUX3_DRAFT_RATES[mode]
        : FLUX3_FULL_RATES[mode][normalizedResolution];

    if (duration === "auto") {
        return `${formatNumber(rate)} BFL credits/s`;
    }

    return credits(rate * Number(duration));
}


// ---------------------------------------------------------------------------
// Price rules
//
// For deprecated FLUX 1 endpoints without a current public fixed-price table,
// the exact submit-response cost replaces the placeholder immediately after run.
// ---------------------------------------------------------------------------

const PRICE_RULES = {
    // FLUX 1
    "FLUX 1.0 [pro]": (node) =>
        actualOrEstimate(node, () => "BFL credits after run"),

    "FLUX 1.0 [dev]": (node) =>
        actualOrEstimate(node, () => "BFL credits after run"),

    "FLUX 1.1 [pro]": (node) =>
        actualOrEstimate(node, () => credits(4)),

    "FLUX 1.1 [ultra]": (node) =>
        actualOrEstimate(node, () => credits(6)),

    "FLUX 1.0 [fill]": (node) =>
        actualOrEstimate(node, () => credits(5)),

    "FLUX 1.0 [depth]": (node) =>
        actualOrEstimate(node, () => "BFL credits after run"),

    "FLUX 1.0 [canny]": (node) =>
        actualOrEstimate(node, () => "BFL credits after run"),

    "FLUX 1.0 [pro] Finetuned": (node) =>
        actualOrEstimate(node, () => "BFL credits after run"),

    "FLUX 1.0 [canny] Finetuned": (node) =>
        actualOrEstimate(node, () => "BFL credits after run"),

    "FLUX 1.0 [depth] Finetuned": (node) =>
        actualOrEstimate(node, () => "BFL credits after run"),

    "FLUX 1.0 [fill] Finetuned": (node) =>
        actualOrEstimate(node, () => "BFL credits after run"),

    "FLUX 1.1 [ultra] Finetuned": (node) =>
        actualOrEstimate(node, () => "BFL credits after run"),

    // FLUX 2
    "FLUX.2 [pro]": (node) =>
        actualOrEstimate(node, flux2ProPrice),

    "FLUX.2 [pro] Preview": (node) =>
        actualOrEstimate(node, flux2ProPrice),

    "FLUX.2 [max]": (node) =>
        actualOrEstimate(node, flux2MaxPrice),

    "FLUX.2 [flex]": (node) =>
        actualOrEstimate(node, flux2FlexPrice),

    // FLUX 3
    "FLUX 3 Text to Video [BFL API]": (node) =>
        actualOrEstimate(node, (n) => flux3Price(n, "t2v")),

    "FLUX 3 Image to Video [BFL API]": (node) =>
        actualOrEstimate(node, (n) => flux3Price(n, "i2v")),

    "FLUX 3 Video Continuation [BFL API]": (node) =>
        actualOrEstimate(node, (n) => flux3Price(n, "v2v")),

    "FLUX 3 Draft Enhance [BFL API]": (node) =>
        actualOrEstimate(node, () => "BFL credits after run"),

    "FLUX 3 Video": (node) =>
        actualOrEstimate(node, flux3LegacyPrice),

    // Account utility
    "BFL Credits": () => "0 BFL credits/Run",
};


// ---------------------------------------------------------------------------
// Badge implementation
// ---------------------------------------------------------------------------

class BFLPriceBadge {
    constructor(getText) {
        this.getText = getText;
        this.fgColor = "#555555";
        this.bgColor = "#f3eee8";
        this.fontSize = 12;
        this.padding = 7;
        this.height = 20;
        this.cornerRadius = 10;
        this.xOffset = 0;
        this.yOffset = 0;
        this._boundingRect = [0, 0, 0, 0];
    }

    get text() {
        try {
            return this.getText() ?? "";
        } catch (error) {
            console.warn("[BFL] Pricing badge error:", error);
            return "";
        }
    }

    get visible() {
        return this.text.length > 0;
    }

    get boundingRect() {
        return this._boundingRect;
    }

    getWidth(ctx) {
        if (!this.visible) {
            return 0;
        }

        const oldFont = ctx.font;
        ctx.font = `${this.fontSize}px sans-serif`;
        const textWidth = ctx.measureText(this.text).width;
        ctx.font = oldFont;

        return 11 + textWidth + this.padding * 2;
    }

    draw(ctx, x, y) {
        if (!this.visible) {
            return;
        }

        x += this.xOffset;
        y += this.yOffset;

        const oldFont = ctx.font;
        const oldFill = ctx.fillStyle;
        const oldBaseline = ctx.textBaseline;
        const oldAlign = ctx.textAlign;

        ctx.font = `${this.fontSize}px sans-serif`;

        const width = this.getWidth(ctx);
        this._boundingRect.splice(0, 4, x, y, width, this.height);

        ctx.fillStyle = this.bgColor;
        ctx.beginPath();

        if (ctx.roundRect) {
            ctx.roundRect(x, y, width, this.height, this.cornerRadius);
        } else {
            ctx.rect(x, y, width, this.height);
        }

        ctx.fill();

        const centerY = y + this.height / 2;
        const iconX = x + this.padding + 3;

        // Small orange diamond, visually close to Comfy's pricing badge icon.
        ctx.save();
        ctx.translate(iconX, centerY);
        ctx.rotate(Math.PI / 4);
        ctx.fillStyle = "#f5a623";
        ctx.fillRect(-3, -3, 6, 6);
        ctx.restore();

        ctx.fillStyle = this.fgColor;
        ctx.textBaseline = "middle";
        ctx.textAlign = "left";
        ctx.fillText(
            this.text,
            x + this.padding + 13,
            centerY + 1
        );

        ctx.font = oldFont;
        ctx.fillStyle = oldFill;
        ctx.textBaseline = oldBaseline;
        ctx.textAlign = oldAlign;
    }
}


// ---------------------------------------------------------------------------
// Comfy extension
// ---------------------------------------------------------------------------

app.registerExtension({
    name: "HMR.BFL.PriceBadges",

    beforeRegisterNodeDef(nodeType, nodeData) {
        const nodeName = nodeData?.name ?? nodeType?.comfyClass ?? nodeType?.type;

        if (!PRICE_RULES[nodeName]) {
            return;
        }

        const originalOnExecuted = nodeType.prototype.onExecuted;

        nodeType.prototype.onExecuted = function (message) {
            originalOnExecuted?.apply(this, arguments);

            const raw = message?.bfl_cost;
            const value = Array.isArray(raw) ? raw[0] : raw;
            const numeric = Number(value);

            if (Number.isFinite(numeric)) {
                this.__bflActualCost = numeric;
                app.canvas?.setDirty(true, true);
            }
        };
    },

    nodeCreated(node) {
        const nodeName =
            node.comfyClass ??
            node.constructor?.comfyClass ??
            node.constructor?.nodeData?.name ??
            node.type;

        const priceRule = PRICE_RULES[nodeName];

        if (!priceRule) {
            return;
        }

        node.badgePosition = "top-right";

        if (!node.badges) {
            node.badges = [];
        }

        const badge = new BFLPriceBadge(() => priceRule(node));
        node.badges.push(() => badge);

        // Repaint when pricing widgets are changed. The getter always reads
        // current widget/socket values, so a redraw is enough.
        for (const w of node.widgets ?? []) {
            if (!["duration", "resolution", "draft", "width", "height"].includes(w.name)) {
                continue;
            }

            const originalCallback = w.callback;

            w.callback = function (...args) {
                const result = originalCallback?.apply(this, args);
                node.__bflActualCost = undefined;
                app.canvas?.setDirty(true, true);
                return result;
            };
        }

        const originalConnectionsChange = node.onConnectionsChange;

        node.onConnectionsChange = function (...args) {
            const result = originalConnectionsChange?.apply(this, args);
            node.__bflActualCost = undefined;
            app.canvas?.setDirty(true, true);
            return result;
        };

        app.canvas?.setDirty(true, true);
    },
});
