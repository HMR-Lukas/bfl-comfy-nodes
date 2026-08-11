import { app } from "../../scripts/app.js";

/*
 * BFL Direct API pricing badges.
 *
 * IMPORTANT:
 * These are BFL credits, not Comfy Credits.
 *
 * This implementation deliberately does NOT set:
 *
 *     nodeData.api_node = true
 *
 * Therefore the nodes remain normal custom nodes.
 */


// ------------------------------------------------------------
// Pricing
// ------------------------------------------------------------

const FULL_RATES = {
    t2v: {
        "720p": 17,
        "1080p": 29,
    },

    i2v: {
        "720p": 17,
        "1080p": 29,
    },

    v2v: {
        "720p": 43,
        "1080p": 54,
    },
};


const DRAFT_RATES = {
    t2v: 6,
    i2v: 6,
    v2v: 12,
};


// ------------------------------------------------------------
// Helpers
// ------------------------------------------------------------

function getWidget(node, name) {
    return node.widgets?.find((widget) => widget.name === name);
}


function getWidgetValue(node, name, fallback = undefined) {
    const widget = getWidget(node, name);

    if (!widget) {
        return fallback;
    }

    return widget.value;
}


function normalizeResolution(value) {
    if (value === "1080p" || value === "fhd") {
        return "1080p";
    }

    return "720p";
}


function calculateFlux3Price(node, mode) {

    const duration =
        getWidgetValue(node, "duration", "auto");

    const resolution =
        normalizeResolution(
            getWidgetValue(node, "resolution", "720p")
        );

    const draft =
        Boolean(
            getWidgetValue(node, "draft", false)
        );


    const rate = draft
        ? DRAFT_RATES[mode]
        : FULL_RATES[mode][resolution];


    if (duration === "auto") {
        return `${rate} BFL credits/s`;
    }


    const seconds = Number(duration);

    if (!Number.isFinite(seconds)) {
        return `${rate} BFL credits/s`;
    }


    const credits = rate * seconds;

    return `${credits} BFL credits/Run`;
}


function calculateLegacyFlux3Price(node) {

    const selectedMode =
        getWidgetValue(node, "mode", "t2v");

    const mode =
        selectedMode === "v2v"
            ? "v2v"
            : selectedMode === "i2v"
                ? "i2v"
                : "t2v";

    return calculateFlux3Price(node, mode);
}


// ------------------------------------------------------------
// Node pricing rules
// ------------------------------------------------------------

const PRICE_RULES = {

    "FLUX 3 Text to Video [BFL API]": (node) =>
        calculateFlux3Price(node, "t2v"),


    "FLUX 3 Image to Video [BFL API]": (node) =>
        calculateFlux3Price(node, "i2v"),


    "FLUX 3 Video Continuation [BFL API]": (node) =>
        calculateFlux3Price(node, "v2v"),


    "FLUX 3 Draft Enhance [BFL API]": () =>
        "BFL cost after submit",


    // Old workflow compatibility node
    "FLUX 3 Video": (node) =>
        calculateLegacyFlux3Price(node),


    // Older direct BFL nodes
    "FLUX 1.1 [pro]": () =>
        "4 BFL credits/Run",


    "FLUX 1.1 [ultra]": () =>
        "6 BFL credits/Run",


    "FLUX 1.0 [fill]": () =>
        "5 BFL credits/Run",
};


// ------------------------------------------------------------
// Badge implementation
//
// This implements the interface ComfyUI expects from an
// LGraphBadge without marking our node as an API/Partner node.
// ------------------------------------------------------------

class BFLPriceBadge {

    constructor(getText) {

        this.getText = getText;

        this.fgColor = "#555555";

        // Similar light background to Comfy's native price badge.
        this.bgColor = "#f3eee8";

        this.fontSize = 12;

        this.padding = 7;

        this.height = 20;

        this.cornerRadius = 10;

        this.xOffset = 0;

        this.yOffset = 0;

        this._boundingRect = [
            0,
            0,
            0,
            0,
        ];
    }


    get text() {
        try {
            return this.getText() ?? "";
        }
        catch (error) {
            console.warn(
                "[BFL] Could not calculate pricing badge:",
                error
            );

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


        ctx.font =
            `${this.fontSize}px sans-serif`;


        const textWidth =
            ctx.measureText(this.text).width;


        ctx.font = oldFont;


        // icon + padding + text
        const iconWidth = 11;

        return (
            iconWidth
            + textWidth
            + this.padding * 2
        );
    }


    draw(ctx, x, y) {

        if (!this.visible) {
            return;
        }


        x += this.xOffset;

        y += this.yOffset;


        const oldFont =
            ctx.font;

        const oldFillStyle =
            ctx.fillStyle;

        const oldStrokeStyle =
            ctx.strokeStyle;

        const oldTextBaseline =
            ctx.textBaseline;

        const oldTextAlign =
            ctx.textAlign;


        ctx.font =
            `${this.fontSize}px sans-serif`;


        const width =
            this.getWidth(ctx);


        this._boundingRect.splice(
            0,
            4,
            x,
            y,
            width,
            this.height
        );


        // ----------------------------------------
        // Background
        // ----------------------------------------

        ctx.fillStyle =
            this.bgColor;


        ctx.beginPath();


        if (ctx.roundRect) {

            ctx.roundRect(
                x,
                y,
                width,
                this.height,
                this.cornerRadius
            );
        }
        else {

            ctx.rect(
                x,
                y,
                width,
                this.height
            );
        }


        ctx.fill();


        // ----------------------------------------
        // Small BFL-style orange icon
        // ----------------------------------------

        const centerY =
            y + this.height / 2;


        const iconX =
            x + this.padding + 3;


        ctx.save();


        ctx.translate(
            iconX,
            centerY
        );


        ctx.rotate(
            Math.PI / 4
        );


        ctx.fillStyle =
            "#f5a623";


        ctx.fillRect(
            -3,
            -3,
            6,
            6
        );


        ctx.restore();


        // ----------------------------------------
        // Text
        // ----------------------------------------

        ctx.fillStyle =
            this.fgColor;


        ctx.textBaseline =
            "middle";


        ctx.textAlign =
            "left";


        ctx.fillText(
            this.text,
            x + this.padding + 13,
            centerY + 1
        );


        // ----------------------------------------
        // Restore canvas
        // ----------------------------------------

        ctx.font =
            oldFont;

        ctx.fillStyle =
            oldFillStyle;

        ctx.strokeStyle =
            oldStrokeStyle;

        ctx.textBaseline =
            oldTextBaseline;

        ctx.textAlign =
            oldTextAlign;
    }
}


// ------------------------------------------------------------
// Comfy extension
// ------------------------------------------------------------

app.registerExtension({

    name: "HMR.BFL.DirectPriceBadges",


    nodeCreated(node) {

        const nodeName =
            node.comfyClass
            ?? node.constructor?.comfyClass
            ?? node.constructor?.nodeData?.name
            ?? node.type;


        const priceRule =
            PRICE_RULES[nodeName];


        if (!priceRule) {
            return;
        }


        /*
         * Important:
         *
         * We deliberately leave the node as a normal custom node.
         *
         * NO:
         *
         * nodeData.api_node = true
         */


        node.badgePosition =
            "top-right";


        const badge =
            new BFLPriceBadge(
                () => priceRule(node)
            );


        if (!node.badges) {
            node.badges = [];
        }


        node.badges.push(
            () => badge
        );


        app.canvas?.setDirty(
            true,
            true
        );
    },
});