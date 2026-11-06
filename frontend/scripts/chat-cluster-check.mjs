// Run against a local API serving docs/design/demo-250.json, never a real scan.
// npm run chat:cluster:check -- http://127.0.0.1:8911
import { execFileSync } from "node:child_process";

const url = process.argv[2];
if (!url || !/^http:\/\/(127\.0\.0\.1|localhost):\d+\/?$/.test(url)) throw new Error("Pass the loopback URL of the demo-250 fixture server");
const session = execFileSync("agent-browser", ["session", "id", "--scope", "worktree", "--prefix", "chat-cluster"], { encoding: "utf8" }).trim();
const browser = (...args) => execFileSync("agent-browser", ["--session", session, ...args], { encoding: "utf8", timeout: 30000 });
const check = (condition, message) => browser("eval", `if (!(${condition})) throw new Error(${JSON.stringify(message)}); true`);
const card = 'document.querySelector(\'section[aria-labelledby="cluster-title"]:not([data-leaving])\')';
// A panel plays its exit before it unmounts (data-leaving), so "gone" means "not live"; the final unmount is waited for below.
const brief = 'document.querySelector(\'section[aria-labelledby="brief-title"]:not([data-leaving])\')';
const chat = 'document.querySelector("#chat-panel:not([data-leaving])")';
try {
  for (const width of [1440, 700, 390]) {
    browser("set", "viewport", String(width), "900");
    browser("open", url);
    browser("eval", 'localStorage.setItem("constellation.brief", "open")');
    browser("open", url);
    browser("wait", "--text", "Where your context goes");
    browser("find", "role", "button", "click", "--name", "24 clusters");
    browser("find", "role", "option", "click", "--name", "Tidy the changelog 28");
    browser("wait", "--fn", `!!${card}`);
    check(`!${brief} && !${chat}`, "Entering a cluster occupies the left slot");
    if (width <= 640) {
      check(`document.querySelector("#ask-trigger").getBoundingClientRect().bottom <= ${card}.getBoundingClientRect().top`, "Phone Chat trigger clears the cluster sheet");
    }
    browser("find", "role", "button", "click", "--name", "Ask");
    browser("wait", "--fn", `!!${chat} && ${chat}.getBoundingClientRect().bottom <= innerHeight + 1`);
    check(`!${card} && !${brief}`, "Opening Chat releases the cluster card and Brief slot");
    check('!location.hash.includes("cluster=")', "Opening Chat exits cluster focus without a stale history entry");
    browser("find", "role", "button", "click", "--name", "Collapse local chat");
    browser("wait", "--fn", `!!${brief}`);
    browser("find", "role", "button", "click", "--name", "Ask");
    browser("find", "role", "button", "click", "--name", "24 clusters");
    browser("find", "role", "option", "click", "--name", "Tidy the changelog 28");
    browser("wait", "--fn", `!!${card}`);
    check(`!${chat} && !${brief}`, "Entering cluster focus closes Chat");
    check('document.activeElement?.id === "cluster-title"', "Keyboard cluster entry focuses its heading");
    if (width < 960) {
      browser("eval", `${card}.querySelector('section[aria-labelledby="card-top"] button').click()`);
      browser("wait", "--fn", '!!document.querySelector("aside") && document.querySelector("aside").getAnimations().every(a => a.playState === "finished")');
      check(`!${card} && !${chat}`, "Narrow Inspector replaces the cluster card");
      browser("find", "role", "button", "click", "--name", "Ask");
      browser("wait", "--fn", `!!${chat} && ${chat}.getBoundingClientRect().bottom <= innerHeight + 1`);
      check('!document.querySelector("aside")', "Narrow Chat replaces the selected Inspector");
      browser("find", "role", "button", "click", "--name", "Collapse local chat");
      browser("wait", "--fn", '!!document.querySelector("aside") && document.querySelector("aside").getAnimations().every(a => a.playState === "finished")');
      browser("find", "role", "button", "click", "--name", "Close inspector");
      browser("press", "b");
      browser("wait", "--fn", `!!${brief}`);
      browser("find", "role", "button", "click", "--name", "24 clusters");
      browser("find", "role", "option", "click", "--name", "Tidy the changelog 28");
      browser("wait", "--fn", `!!${card}`);
    }
    browser("back");
    browser("wait", "--fn", `!!${brief}`);
    check(`!${chat} && !${card}`, "Browser Back restores Brief and the whole map");
    console.log(`Shared panels and history passed at ${width}px.`);
  }
  console.log("Demo Chat, Brief and cluster focus share one left slot and preserve Back navigation.");
} finally {
  browser("close");
}
