(function () {
  var root = document.getElementById("studio");
  var initialNode = document.getElementById("studio-initial");
  var form = document.getElementById("page-form");
  if (!root || !initialNode || !form) return;

  var initial = JSON.parse(initialNode.textContent || "{}");
  var blocks = Array.isArray(initial.blocks) ? initial.blocks : [];
  var images = Array.isArray(initial.images) ? initial.images : [];
  var mode = initial.mode === "design" ? "design" : "html";
  var selected = blocks.length ? 0 : -1;

  var stage = document.getElementById("studio-stage");
  var inspector = document.getElementById("studio-inspector");
  var htmlPanel = document.getElementById("studio-html");
  var layout = document.getElementById("studio-layout");
  var body = document.getElementById("body");
  var modeField = document.getElementById("studio_mode");
  var blocksField = document.getElementById("blocks");

  function blank(type) {
    if (type === "heading") return { type: "heading", text: "Heading", level: 2 };
    if (type === "text") return { type: "text", text: "Write the paragraph." };
    if (type === "image") return { type: "image", media_id: images.length ? images[0].id : 0, alt: "" };
    if (type === "button") return { type: "button", label: "Learn more", href: "/" };
    if (type === "quote") return { type: "quote", text: "A quotation.", cite: "" };
    if (type === "list") return { type: "list", items: ["First point"], ordered: false };
    if (type === "columns") return { type: "columns", left: "Left column", right: "Right column" };
    return { type: "divider" };
  }

  function field(label, node) {
    var wrap = document.createElement("label");
    wrap.textContent = label;
    wrap.appendChild(node);
    return wrap;
  }

  function input(value, oninput) {
    var node = document.createElement("input");
    node.value = value || "";
    node.addEventListener("input", function () { oninput(node.value); drawStage(); });
    return node;
  }

  function area(value, oninput) {
    var node = document.createElement("textarea");
    node.value = value || "";
    node.addEventListener("input", function () { oninput(node.value); drawStage(); });
    return node;
  }

  function show(next) {
    mode = next;
    modeField.value = mode;
    layout.hidden = mode !== "design";
    htmlPanel.hidden = mode !== "html";
    var tabs = root.querySelectorAll("[data-studio-tab]");
    for (var i = 0; i < tabs.length; i++) {
      tabs[i].setAttribute("aria-pressed", tabs[i].getAttribute("data-studio-tab") === mode ? "true" : "false");
    }
    if (mode === "design" && blocks.length === 0 && body.value.trim()) {
      blocks.push({ type: "html", html: body.value });
      selected = 0;
    }
    draw();
  }

  function draw() {
    drawStage();
    drawInspector();
  }

  function drawStage() {
    blocksField.value = JSON.stringify(blocks);
    stage.replaceChildren();
    if (!blocks.length) {
      var empty = document.createElement("p");
      empty.className = "muted";
      empty.textContent = "Add a block from the left. The page is empty.";
      stage.appendChild(empty);
    }
    blocks.forEach(function (block, index) {
      var card = document.createElement("article");
      card.className = "studio-block" + (index === selected ? " selected" : "");
      var preview = document.createElement("div");
      preview.className = "studio-preview";
      preview.appendChild(previewBlock(block));
      card.appendChild(preview);
      var tools = document.createElement("div");
      tools.className = "studio-tools";
      tools.appendChild(tool("Up", function () { move(index, -1); }));
      tools.appendChild(tool("Down", function () { move(index, 1); }));
      tools.appendChild(tool("Remove", function () { remove(index); }));
      card.appendChild(tools);
      card.addEventListener("click", function () { selected = index; draw(); });
      stage.appendChild(card);
    });
  }

  function previewBlock(block) {
    if (block.type === "heading") {
      return document.createElement(block.level === 3 ? "h3" : "h2").appendChild(textNode(block.text || "Heading")).parentNode;
    }
    if (block.type === "text") {
      var p = document.createElement("p");
      p.textContent = block.text || "";
      return p;
    }
    if (block.type === "image") {
      var found = images.filter(function (image) { return image.id === block.media_id; })[0];
      if (!found) {
        var missing = document.createElement("p");
        missing.className = "muted";
        missing.textContent = "Choose an uploaded image.";
        return missing;
      }
      var img = document.createElement("img");
      img.src = "/media/" + found.id;
      img.alt = block.alt || "";
      return img;
    }
    if (block.type === "button") {
      var link = document.createElement("span");
      link.className = "studio-link";
      link.textContent = block.label || "Button";
      return link;
    }
    if (block.type === "quote") {
      var quote = document.createElement("blockquote");
      quote.textContent = block.text || "";
      return quote;
    }
    if (block.type === "list") {
      var list = document.createElement(block.ordered ? "ol" : "ul");
      (block.items || []).forEach(function (item) {
        var li = document.createElement("li");
        li.textContent = item;
        list.appendChild(li);
      });
      return list;
    }
    if (block.type === "columns") {
      var table = document.createElement("table");
      var row = document.createElement("tr");
      ["left", "right"].forEach(function (side) {
        var cell = document.createElement("td");
        cell.textContent = block[side] || "";
        row.appendChild(cell);
      });
      table.appendChild(row);
      return table;
    }
    if (block.type === "html") {
      var custom = document.createElement("p");
      custom.className = "muted";
      custom.textContent = "Custom HTML is saved as safe page content. It is not run in this editor.";
      return custom;
    }
    var line = document.createElement("hr");
    return line;
  }

  function textNode(value) {
    return document.createTextNode(value);
  }

  function tool(label, action) {
    var button = document.createElement("button");
    button.type = "button";
    button.className = "btn secondary";
    button.textContent = label;
    button.addEventListener("click", function (event) {
      event.stopPropagation();
      action();
    });
    return button;
  }

  function move(index, step) {
    var next = index + step;
    if (next < 0 || next >= blocks.length) return;
    var hold = blocks[index];
    blocks[index] = blocks[next];
    blocks[next] = hold;
    selected = next;
    draw();
  }

  function remove(index) {
    blocks.splice(index, 1);
    selected = Math.min(selected, blocks.length - 1);
    draw();
  }

  function drawInspector() {
    inspector.replaceChildren();
    var names = { heading: "Heading", text: "Text", image: "Image", button: "Button", quote: "Quote", list: "List", columns: "Columns", divider: "Divider", html: "HTML" };
    var title = document.createElement("h2");
    title.textContent = selected >= 0 && blocks[selected] ? names[blocks[selected].type] || "Block" : "Block";
    inspector.appendChild(title);
    if (selected < 0 || !blocks[selected]) {
      var note = document.createElement("p");
      note.className = "muted";
      note.textContent = "Select a block on the page.";
      inspector.appendChild(note);
      return;
    }
    var block = blocks[selected];
    if (block.type === "heading") {
      inspector.appendChild(field("Heading", input(block.text, function (value) { block.text = value; })));
      var level = document.createElement("select");
      [["2", "Large"], ["3", "Medium"]].forEach(function (pair) {
        var option = document.createElement("option");
        option.value = pair[0];
        option.textContent = pair[1];
        if (String(block.level || 2) === pair[0]) option.selected = true;
        level.appendChild(option);
      });
      level.addEventListener("change", function () { block.level = Number(level.value); drawStage(); });
      inspector.appendChild(field("Size", level));
    } else if (block.type === "text") {
      inspector.appendChild(field("Paragraph", area(block.text, function (value) { block.text = value; })));
    } else if (block.type === "image") {
      var select = document.createElement("select");
      var none = document.createElement("option");
      none.value = "0";
      none.textContent = "Choose an image";
      select.appendChild(none);
      images.forEach(function (image) {
        var option = document.createElement("option");
        option.value = String(image.id);
        option.textContent = image.name;
        if (image.id === block.media_id) option.selected = true;
        select.appendChild(option);
      });
      select.addEventListener("change", function () { block.media_id = Number(select.value); drawStage(); });
      inspector.appendChild(field("Image", select));
      inspector.appendChild(field("Description", input(block.alt, function (value) { block.alt = value; })));
    } else if (block.type === "button") {
      inspector.appendChild(field("Label", input(block.label, function (value) { block.label = value; })));
      inspector.appendChild(field("Link", input(block.href, function (value) { block.href = value; })));
    } else if (block.type === "quote") {
      inspector.appendChild(field("Quotation", area(block.text, function (value) { block.text = value; })));
      inspector.appendChild(field("Source", input(block.cite, function (value) { block.cite = value; })));
    } else if (block.type === "list") {
      inspector.appendChild(field("One item per line", area((block.items || []).join("\n"), function (value) {
        block.items = value.split("\n");
      })));
      var ordered = document.createElement("input");
      ordered.type = "checkbox";
      ordered.checked = block.ordered === true;
      ordered.addEventListener("change", function () { block.ordered = ordered.checked; drawStage(); });
      var check = document.createElement("label");
      check.className = "check";
      check.appendChild(ordered);
      check.appendChild(document.createTextNode(" Numbered"));
      inspector.appendChild(check);
    } else if (block.type === "columns") {
      inspector.appendChild(field("Left", area(block.left, function (value) { block.left = value; })));
      inspector.appendChild(field("Right", area(block.right, function (value) { block.right = value; })));
    } else if (block.type === "html") {
      inspector.appendChild(field("HTML", area(block.html, function (value) { block.html = value; })));
      var help = document.createElement("p");
      help.className = "muted";
      help.textContent = "Scripts are removed when the page is saved.";
      inspector.appendChild(help);
    } else {
      var divider = document.createElement("p");
      divider.className = "muted";
      divider.textContent = "A horizontal line between sections.";
      inspector.appendChild(divider);
    }
  }

  root.querySelectorAll("[data-add]").forEach(function (button) {
    button.addEventListener("click", function () {
      blocks.push(blank(button.getAttribute("data-add")));
      selected = blocks.length - 1;
      show("design");
    });
  });
  root.querySelectorAll("[data-studio-tab]").forEach(function (button) {
    button.addEventListener("click", function () { show(button.getAttribute("data-studio-tab")); });
  });
  form.addEventListener("submit", function () {
    modeField.value = mode;
    blocksField.value = JSON.stringify(blocks);
  });
  show(mode);
})();
