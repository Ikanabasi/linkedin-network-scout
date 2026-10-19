(() => {

    if (
        window.__NETWORK_SCOUT_COMMENT_ACTION__
    ) {

        return;
    }


    window.__NETWORK_SCOUT_COMMENT_ACTION__ =
        true;


    const PAGE_TIMEOUT_MS =
        20000;

    const COMMENT_BOX_TIMEOUT_MS =
        15000;

    const VERIFY_TIMEOUT_MS =
        20000;


    // ======================================================
    // HELPERS
    // ======================================================

    function sleep(
        ms
    ) {

        return new Promise(
            (resolve) => {

                setTimeout(
                    resolve,
                    ms
                );
            }
        );
    }


    function normalizeText(
        value
    ) {

        return (
            value
            ||
            ""
        )
            .replace(
                /\u200b/g,
                ""
            )
            .replace(
                /\s+/g,
                " "
            )
            .trim();
    }


    function lowerText(
        value
    ) {

        return normalizeText(
            value
        ).toLowerCase();
    }


    function isVisible(
        element
    ) {

        if (!element) {

            return false;
        }


        try {

            const style =
                window.getComputedStyle(
                    element
                );


            if (
                style.display ===
                    "none"
                ||
                style.visibility ===
                    "hidden"
                ||
                Number(
                    style.opacity
                ) === 0
            ) {

                return false;
            }


            const rect =
                element.getBoundingClientRect();


            return (
                rect.width > 0
                &&
                rect.height > 0
            );

        } catch (
            error
        ) {

            return false;
        }
    }


    function clickElement(
        element
    ) {

        if (!element) {

            return false;
        }


        try {

            element.scrollIntoView(
                {
                    block:
                        "center",

                    inline:
                        "center"
                }
            );

        } catch (
            error
        ) {

            // Ignore.
        }


        try {

            element.click();

            return true;

        } catch (
            error
        ) {

            try {

                element.dispatchEvent(
                    new MouseEvent(
                        "click",
                        {
                            bubbles:
                                true,

                            cancelable:
                                true,

                            view:
                                window
                        }
                    )
                );


                return true;

            } catch (
                secondError
            ) {

                return false;
            }
        }
    }


    // ======================================================
    // LINKEDIN ACCESS CHECK
    // ======================================================

    function detectNeedsAttention() {

        const url =
            window.location.href
                .toLowerCase();


        if (
            url.includes(
                "/login"
            )
            ||
            url.includes(
                "/checkpoint/"
            )
            ||
            url.includes(
                "/challenge/"
            )
            ||
            url.includes(
                "/authwall"
            )
        ) {

            return (
                "LinkedIn requires login "
                +
                "or security verification."
            );
        }


        const visibleDialogs =
            Array.from(
                document.querySelectorAll(
                    [
                        "[role='dialog']",
                        "[role='alert']"
                    ].join(",")
                )
            )
            .filter(
                isVisible
            );


        const phrases = [
            "verify your identity",
            "security verification",
            "quick security check",
            "captcha"
        ];


        for (
            const dialog
            of visibleDialogs
        ) {

            const text =
                lowerText(
                    dialog.innerText
                    ||
                    dialog.textContent
                );


            for (
                const phrase
                of phrases
            ) {

                if (
                    text.includes(
                        phrase
                    )
                ) {

                    return (
                        "LinkedIn requires "
                        +
                        "security verification."
                    );
                }
            }
        }


        return null;
    }


    // ======================================================
    // ACTIVITY ID
    // ======================================================

    function extractActivityId(
        value
    ) {

        if (!value) {

            return null;
        }


        let decoded =
            String(
                value
            );


        try {

            decoded =
                decodeURIComponent(
                    decoded
                );

        } catch (
            error
        ) {

            // Keep original.
        }


        const matches = [
            decoded.match(
                /urn:li:activity:(\d+)/i
            ),

            decoded.match(
                /activity-(\d+)/i
            )
        ];


        for (
            const match
            of matches
        ) {

            if (
                match
                &&
                match[1]
            ) {

                return match[1];
            }
        }


        return null;
    }


    // ======================================================
    // POST CONTAINER
    // ======================================================

    function findPostContainer(
        requestedPostUrl
    ) {

        const activityId =
            extractActivityId(
                requestedPostUrl
            );


        if (activityId) {

            const links =
                Array.from(
                    document.querySelectorAll(
                        "a[href]"
                    )
                );


            for (
                const link
                of links
            ) {

                if (
                    !String(
                        link.href
                    )
                    .includes(
                        activityId
                    )
                ) {

                    continue;
                }


                const article =
                    link.closest(
                        "article"
                    );


                if (article) {

                    return article;
                }


                let current =
                    link;


                for (
                    let index = 0;
                    index < 10;
                    index += 1
                ) {

                    current =
                        current
                            ?.parentElement;


                    if (!current) {

                        break;
                    }


                    const textLength =
                        normalizeText(
                            current.innerText
                        ).length;


                    const buttons =
                        current.querySelectorAll(
                            "button"
                        );


                    if (
                        textLength > 20
                        &&
                        textLength < 15000
                        &&
                        buttons.length > 0
                    ) {

                        return current;
                    }
                }
            }
        }


        const selectors = [
            "[data-view-name='feed-full-update']",
            ".feed-shared-update-v2",
            "article",
            "[role='article']"
        ];


        for (
            const selector
            of selectors
        ) {

            const elements =
                Array.from(
                    document.querySelectorAll(
                        selector
                    )
                )
                .filter(
                    isVisible
                );


            if (
                elements.length === 1
            ) {

                return elements[0];
            }
        }


        const main =
            document.querySelector(
                "main"
            );


        if (
            main
            &&
            isVisible(
                main
            )
        ) {

            return main;
        }


        return document.body;
    }


    // ======================================================
    // COMMENT ACTION BUTTON
    // ======================================================

    function findCommentActionButton(
        container
    ) {

        const buttons =
            Array.from(
                container.querySelectorAll(
                    [
                        "button",
                        "[role='button']"
                    ].join(",")
                )
            )
            .filter(
                isVisible
            );


        for (
            const button
            of buttons
        ) {

            const visibleText =
                lowerText(
                    button.innerText
                    ||
                    button.textContent
                );


            const aria =
                lowerText(
                    button.getAttribute(
                        "aria-label"
                    )
                );


            if (
                visibleText ===
                    "comment"
                ||
                aria ===
                    "comment"
                ||
                aria.startsWith(
                    "comment "
                )
            ) {

                return button;
            }
        }


        return null;
    }


    // ======================================================
    // COMMENT EDITOR
    // ======================================================

    function findCommentEditor(
        container
    ) {

        const selectors = [
            ".comments-comment-box__contenteditable",
            "[contenteditable='true'][role='textbox']",
            "[contenteditable='true'][aria-label*='comment' i]",
            "textarea[aria-label*='comment' i]",
            "textarea[placeholder*='comment' i]"
        ];


        for (
            const selector
            of selectors
        ) {

            const elements =
                Array.from(
                    container.querySelectorAll(
                        selector
                    )
                )
                .filter(
                    isVisible
                );


            if (
                elements.length > 0
            ) {

                return elements[
                    elements.length - 1
                ];
            }
        }


        const allEditors =
            Array.from(
                container.querySelectorAll(
                    [
                        "[contenteditable='true']",
                        "textarea"
                    ].join(",")
                )
            )
            .filter(
                isVisible
            );


        for (
            const editor
            of allEditors
        ) {

            const label =
                lowerText(
                    (
                        editor.getAttribute(
                            "aria-label"
                        )
                        ||
                        ""
                    )
                    +
                    " "
                    +
                    (
                        editor.getAttribute(
                            "placeholder"
                        )
                        ||
                        ""
                    )
                );


            const parentText =
                lowerText(
                    editor.parentElement
                        ?.innerText
                );


            if (
                label.includes(
                    "comment"
                )
                ||
                parentText.includes(
                    "comment"
                )
            ) {

                return editor;
            }
        }


        return null;
    }


    async function waitForCommentEditor(
        container
    ) {

        const startedAt =
            Date.now();


        while (
            Date.now()
            -
            startedAt
            <
            COMMENT_BOX_TIMEOUT_MS
        ) {

            const editor =
                findCommentEditor(
                    container
                );


            if (editor) {

                return editor;
            }


            await sleep(
                300
            );
        }


        return null;
    }


    // ======================================================
    // TYPE EXACT TEXT
    // ======================================================

    function setNativeValue(
        element,
        value
    ) {

        const prototype =
            Object.getPrototypeOf(
                element
            );


        const descriptor =
            Object.getOwnPropertyDescriptor(
                prototype,
                "value"
            );


        if (
            descriptor
            &&
            descriptor.set
        ) {

            descriptor.set.call(
                element,
                value
            );

        } else {

            element.value =
                value;
        }


        element.dispatchEvent(
            new Event(
                "input",
                {
                    bubbles:
                        true
                }
            )
        );
    }


    function typeExactText(
        editor,
        commentText
    ) {

        editor.focus();


        if (
            editor.tagName ===
                "TEXTAREA"
            ||
            editor.tagName ===
                "INPUT"
        ) {

            setNativeValue(
                editor,
                commentText
            );


            return (
                normalizeText(
                    editor.value
                )
                ===
                normalizeText(
                    commentText
                )
            );
        }


        try {

            const selection =
                window.getSelection();


            const range =
                document.createRange();


            range.selectNodeContents(
                editor
            );


            selection.removeAllRanges();

            selection.addRange(
                range
            );


            document.execCommand(
                "delete",
                false,
                null
            );


            document.execCommand(
                "insertText",
                false,
                commentText
            );


            editor.dispatchEvent(
                new InputEvent(
                    "input",
                    {
                        bubbles:
                            true,

                        inputType:
                            "insertText",

                        data:
                            commentText
                    }
                )
            );

        } catch (
            error
        ) {

            editor.textContent =
                commentText;


            editor.dispatchEvent(
                new Event(
                    "input",
                    {
                        bubbles:
                            true
                    }
                )
            );
        }


        return (
            normalizeText(
                editor.innerText
                ||
                editor.textContent
            )
            ===
            normalizeText(
                commentText
            )
        );
    }


    // ======================================================
    // COMPOSER ROOT
    // ======================================================

    function findComposerRoot(
        editor
    ) {

        const form =
            editor.closest(
                "form"
            );


        if (form) {

            return form;
        }


        let current =
            editor;


        for (
            let index = 0;
            index < 8;
            index += 1
        ) {

            current =
                current
                    ?.parentElement;


            if (!current) {

                break;
            }


            const buttons =
                current.querySelectorAll(
                    "button"
                );


            if (
                buttons.length > 0
                &&
                normalizeText(
                    current.innerText
                ).length < 5000
            ) {

                return current;
            }
        }


        return editor.parentElement;
    }


    // ======================================================
    // SUBMIT BUTTON
    // ======================================================

    function findSubmitButton(
        editor
    ) {

        const root =
            findComposerRoot(
                editor
            );


        if (!root) {

            return null;
        }


        const buttons =
            Array.from(
                root.querySelectorAll(
                    [
                        "button",
                        "[role='button']"
                    ].join(",")
                )
            )
            .filter(
                isVisible
            )
            .filter(
                (button) => {

                    return !button.disabled;
                }
            );


        const allowed = [
            "comment",
            "post",
            "post comment",
            "submit",
            "send"
        ];


        for (
            const button
            of buttons
        ) {

            const text =
                lowerText(
                    button.innerText
                    ||
                    button.textContent
                );


            const aria =
                lowerText(
                    button.getAttribute(
                        "aria-label"
                    )
                );


            if (
                allowed.includes(
                    text
                )
                ||
                allowed.includes(
                    aria
                )
                ||
                aria.includes(
                    "post comment"
                )
            ) {

                return button;
            }
        }


        return null;
    }


    // ======================================================
    // EXISTING COMMENT CHECK
    // ======================================================

    function findExactPostedComment(
        container,
        commentText,
        editor = null
    ) {

        const target =
            normalizeText(
                commentText
            );


        const candidates =
            Array.from(
                container.querySelectorAll(
                    [
                        "p",
                        "span",
                        "div"
                    ].join(",")
                )
            )
            .filter(
                isVisible
            );


        for (
            const element
            of candidates
        ) {

            if (
                editor
                &&
                (
                    element === editor
                    ||
                    editor.contains(
                        element
                    )
                    ||
                    element.closest(
                        "[contenteditable='true']"
                    )
                )
            ) {

                continue;
            }


            const text =
                normalizeText(
                    element.innerText
                    ||
                    element.textContent
                );


            if (
                text === target
            ) {

                return element;
            }
        }


        return null;
    }


    // ======================================================
    // VERIFY
    // ======================================================

    async function waitForCommentVerification(
        container,
        commentText,
        editor
    ) {

        const startedAt =
            Date.now();


        while (
            Date.now()
            -
            startedAt
            <
            VERIFY_TIMEOUT_MS
        ) {

            const attention =
                detectNeedsAttention();


            if (attention) {

                return {
                    verified:
                        false,

                    submitted:
                        true,

                    status:
                        "needs_attention",

                    verificationText:
                        attention,

                    message:
                        attention
                };
            }


            const posted =
                findExactPostedComment(
                    container,
                    commentText,
                    editor
                );


            if (posted) {

                return {
                    verified:
                        true,

                    submitted:
                        true,

                    status:
                        "verified_comment_posted",

                    verificationText:
                        normalizeText(
                            posted.innerText
                            ||
                            posted.textContent
                        ),

                    message:
                        (
                            "Comment posted and "
                            +
                            "verified on LinkedIn."
                        )
                };
            }


            await sleep(
                500
            );
        }


        return {
            verified:
                false,

            submitted:
                true,

            status:
                "submitted_unverified",

            verificationText:
                null,

            message:
                (
                    "LinkedIn accepted the submit "
                    +
                    "action, but Network Scout "
                    +
                    "could not verify the comment "
                    +
                    "in the rendered discussion."
                )
        };
    }


    // ======================================================
    // MAIN
    // ======================================================

    async function postComment(
        requestedPostUrl,
        commentText
    ) {

        const attention =
            detectNeedsAttention();


        if (attention) {

            return {
                verified:
                    false,

                submitted:
                    false,

                status:
                    "needs_attention",

                verificationText:
                    attention,

                message:
                    attention
            };
        }


        const startedAt =
            Date.now();


        while (
            Date.now()
            -
            startedAt
            <
            PAGE_TIMEOUT_MS
        ) {

            if (
                document.readyState ===
                "complete"
                ||
                document.readyState ===
                "interactive"
            ) {

                break;
            }


            await sleep(
                300
            );
        }


        const container =
            findPostContainer(
                requestedPostUrl
            );


        // Prevent duplicate posting if the exact
        // comment is already visible.

        const existingComment =
            findExactPostedComment(
                container,
                commentText
            );


        if (existingComment) {

            return {
                verified:
                    true,

                submitted:
                    false,

                status:
                    "already_posted",

                verificationText:
                    normalizeText(
                        existingComment.innerText
                        ||
                        existingComment.textContent
                    ),

                message:
                    (
                        "This exact comment is "
                        +
                        "already visible on LinkedIn."
                    )
            };
        }


        let editor =
            findCommentEditor(
                container
            );


        if (!editor) {

            const commentButton =
                findCommentActionButton(
                    container
                );


            if (commentButton) {

                clickElement(
                    commentButton
                );


                await sleep(
                    600
                );
            }


            editor =
                await waitForCommentEditor(
                    container
                );
        }


        if (!editor) {

            return {
                verified:
                    false,

                submitted:
                    false,

                status:
                    "comment_box_not_found",

                verificationText:
                    null,

                message:
                    (
                        "Network Scout could not "
                        +
                        "find LinkedIn's comment box."
                    )
            };
        }


        const typed =
            typeExactText(
                editor,
                commentText
            );


        if (!typed) {

            return {
                verified:
                    false,

                submitted:
                    false,

                status:
                    "typing_failed",

                verificationText:
                    null,

                message:
                    (
                        "Network Scout could not "
                        +
                        "confirm that the exact "
                        +
                        "comment text was inserted."
                    )
            };
        }


        await sleep(
            500
        );


        const submitButton =
            findSubmitButton(
                editor
            );


        if (!submitButton) {

            return {
                verified:
                    false,

                submitted:
                    false,

                status:
                    "submit_button_not_found",

                verificationText:
                    null,

                message:
                    (
                        "The comment was typed, but "
                        +
                        "Network Scout could not find "
                        +
                        "LinkedIn's submit button."
                    )
            };
        }


        const clicked =
            clickElement(
                submitButton
            );


        if (!clicked) {

            return {
                verified:
                    false,

                submitted:
                    false,

                status:
                    "submit_failed",

                verificationText:
                    null,

                message:
                    (
                        "Network Scout found the "
                        +
                        "comment submit button but "
                        +
                        "could not click it."
                    )
            };
        }


        return await waitForCommentVerification(
            container,
            commentText,
            editor
        );
    }


    // ======================================================
    // MESSAGE
    // ======================================================

    chrome.runtime.onMessage.addListener(
        (
            message,
            sender,
            sendResponse
        ) => {

            if (
                message?.type !==
                "NETWORK_SCOUT_POST_COMMENT"
            ) {

                return false;
            }


            postComment(
                message.postUrl,
                String(
                    message.commentText
                    ||
                    ""
                )
            )
                .then(
                    sendResponse
                )
                .catch(
                    (error) => {

                        sendResponse(
                            {
                                verified:
                                    false,

                                submitted:
                                    false,

                                status:
                                    "failed",

                                verificationText:
                                    null,

                                message:
                                    error.message
                            }
                        );
                    }
                );


            return true;
        }
    );

})();