/* Network Scout — comment-only content script. No relationship controls are touched. */
(() => {
  if (globalThis.__networkScoutCommentHandlerInstalled) return;
  globalThis.__networkScoutCommentHandlerInstalled = true;

  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const clean = (value) => String(value || "").replace(/\s+/g, " ").trim();
  const visible = (el) => {
    if (!el || !el.isConnected) return false;
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.display !== "none" && s.visibility !== "hidden";
  };
  const canonicalPost = (value) => {
    try {
      const u = new URL(value, location.origin);
      if (u.protocol !== "https:" || !["linkedin.com", "www.linkedin.com"].includes(u.hostname.toLowerCase())) return null;
      if (!(/^\/feed\/update\/urn:li:activity:\d+\/?$/i.test(u.pathname) || /^\/posts\/[^/]+\/?$/i.test(u.pathname))) return null;
      return `https://www.linkedin.com${u.pathname.replace(/\/$/, "")}`;
    } catch { return null; }
  };
  const actionLabel = (el) => clean([
    el.getAttribute("aria-label"), el.getAttribute("title"), el.innerText, el.textContent
  ].filter(Boolean).join(" ")).toLowerCase();
  const buttons = (root) => [...root.querySelectorAll("button, [role='button']")].filter(visible);
  const fail = (reason) => ({ verified: false, status: "not_verified", message: reason });
  const main = () => document.querySelector("main") || document.querySelector("[role='main']");
  const isEditor = (el) => !!el.closest('[contenteditable="true"], [role="textbox"], textarea');

  async function handle(request) {
    const expected = canonicalPost(request.postUrl);
    const actual = canonicalPost(location.href);
    if (!expected || actual !== expected) return fail("LinkedIn is not on the exact requested post URL. No comment was submitted.");
    const text = clean(request.commentText);
    if (!text || text.length > 1250) return fail("The approved comment is empty or too long.");

    let root = null;
    for (let tries = 0; tries < 15; tries++) {
      root = main();
      if (root && visible(root)) break;
      await sleep(400);
    }
    if (!root || !visible(root)) return fail("The exact LinkedIn post did not finish loading.");

    // A specific post permalink must be present within its page before an action.
    const permalinkPresent = [...root.querySelectorAll("a[href]")]
      .some(a => canonicalPost(a.href) === expected);
    // LinkedIn often omits the permalink anchor on its single-post page. In that
    // case the exact top-level browser URL is the stronger locator.
    if (!permalinkPresent && canonicalPost(location.href) !== expected) return fail("Post identity could not be confirmed.");

    const editors = () => [...root.querySelectorAll('[contenteditable="true"], [role="textbox"], textarea')]
      .filter(visible).filter(el => !el.closest('[role="dialog"]'));

    let editorList = editors();
    if (editorList.length === 0) {
      const commentEntries = buttons(root).filter(el => /^(comment|write a comment)(?:\b|$)/i.test(actionLabel(el)));
      if (commentEntries.length !== 1) return fail("Could not uniquely locate the comment editor for this post. No comment was submitted.");
      commentEntries[0].click();
      for (let i = 0; i < 12; i++) {
        await sleep(350);
        editorList = editors();
        if (editorList.length) break;
      }
    }
    if (editorList.length !== 1) return fail("LinkedIn displayed multiple or no comment editors. Nothing was submitted.");
    const editor = editorList[0];
    editor.focus();
    if (editor.tagName === "TEXTAREA" || editor.tagName === "INPUT") {
      const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")?.set;
      if (!setter) return fail("Could not safely enter the approved comment.");
      setter.call(editor, text);
      editor.dispatchEvent(new Event("input", { bubbles: true }));
      editor.dispatchEvent(new Event("change", { bubbles: true }));
    } else {
      // Browser-supported input events, so React/LinkedIn sees the edit.
      const inserted = document.execCommand("insertText", false, text);
      if (!inserted) return fail("Could not enter the approved comment into LinkedIn's editor.");
      editor.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: text }));
    }
    await sleep(500);
    if (clean(editor.value ?? editor.innerText ?? editor.textContent) !== text) {
      return fail("LinkedIn's editor did not contain the exact approved comment. Nothing was submitted.");
    }

    // Locate one enabled submit control attached to this editor, not an unrelated post.
    let scope = editor.parentElement;
    let submit = null;
    for (let depth = 0; depth < 7 && scope && scope !== document.body; depth++, scope = scope.parentElement) {
      const matches = buttons(scope).filter(el => {
        // LinkedIn labels this action "Comment" on its newer composer.
        // Inspect each label separately: aria-label plus innerText can
        // otherwise produce "Comment Comment" and fail an exact match.
        const labels = [
          el.getAttribute("aria-label"),
          el.getAttribute("title"),
          el.innerText,
          el.textContent
        ].map(clean).filter(Boolean);
        const isSubmit = labels.some(label =>
          /^(?:comment|post|post comment|send)$/i.test(label)
        );
        return isSubmit && !el.disabled &&
          el.getAttribute("aria-disabled") !== "true";
      });
      if (matches.length === 1) { submit = matches[0]; break; }
      if (matches.length > 1) return fail("Multiple Post controls detected. Nothing was submitted.");
    }
    if (!submit) return fail("LinkedIn did not expose an enabled Comment/Post button. No comment was submitted.");
    if (canonicalPost(location.href) !== expected) return fail("LinkedIn navigated away from the selected post. Nothing was submitted.");

    // Capture the pre-submit state. An already-present identical comment is
    // ambiguous and must not be mistaken for proof of this submission.
    const publishedMatches = () => {
      if (canonicalPost(location.href) !== expected) return [];
      const items = [];
      const paragraphs = [...root.querySelectorAll("p, span, div")];
      for (const el of paragraphs) {
        if (!visible(el) || isEditor(el) || el === editor || el.contains(editor)) continue;
        if (clean(el.innerText || el.textContent) !== text) continue;
        // Only count innermost matching text elements.
        if ([...el.children].some(child => clean(child.innerText || child.textContent) === text)) continue;
        let ancestor = el.parentElement;
        for (let depth = 0; depth < 10 && ancestor && ancestor !== root; depth++, ancestor = ancestor.parentElement) {
          if (ancestor.contains(editor)) continue;
          const links = [...ancestor.querySelectorAll('a[href*="/in/"]')]
            .filter(link => visible(link));
          if (links.length === 0) continue;
          // Comment cards on this LinkedIn layout wrap the body and author
          // link several DIVs above the P, with generated CSS class names.
          const body = clean(ancestor.innerText || ancestor.textContent);
          if (body.length > 3000) break; // Don't use the whole feed/main.
          if (body.includes(text)) {
            items.push(el);
            break;
          }
        }
      }
      return items;
    };

    const beforeCount = publishedMatches().length;
    if (beforeCount > 0) {
      return fail("An identical published comment is already visible. No second comment was submitted to prevent a duplicate.");
    }

    submit.click(); // Exactly once; never auto-retry.

    // LinkedIn may publish without showing a toast or dismissing the editor.
    // Confirm a newly rendered copy of the EXACT approved text, outside any
    // editor and within a comment item that has an author profile link.
    for (let attempt = 0; attempt < 40; attempt++) {
      await sleep(500);
      if (publishedMatches().length > beforeCount) {
        return {
          verified: true,
          status: "verified_posted",
          verification_text: "A new matching published comment appeared with an author profile link outside the editor on the exact LinkedIn post."
        };
      }
    }

    return fail("Comment submission was attempted once, but a new published comment could not be verified. Check the post before retrying to avoid a duplicate.");

  }
  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message?.type !== "NETWORK_SCOUT_SUBMIT_COMMENT_IN_PAGE") return false;
    handle(message).then(sendResponse).catch(error => sendResponse(fail(`Comment could not be verified: ${error.message}`)));
    return true;
  });
})();
