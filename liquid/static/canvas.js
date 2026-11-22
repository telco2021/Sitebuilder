(function () {
  var root = document.getElementById("editor");
  var initialNode = document.getElementById("editor-initial");
  var form = document.getElementById("page-form");
  if (!root || !initialNode || !form) return;

  var initial = JSON.parse(initialNode.textContent || "{}");
  var doc = initial.document && Array.isArray(initial.document.content) ? initial.document : { version: 1, content: [] };
  var images = Array.isArray(initial.images) ? initial.images : [];
  var selected = null;
  var history = [];
  var future = [];
  var dragging = null;
  var suppressClick = false;
  var phone = false;

  var stage = document.getElementById("editor-canvas");
  var fields = document.getElementById("inspector-fields");
  var search = document.getElementById("inspector-search");
  var frame = document.getElementById("editor-frame");
  var blocks = document.getElementById("blocks");
  var title = document.getElementById("title");
  var slug = document.getElementById("slug");
  var description = document.getElementById("description");
  var searchTitle = document.getElementById("search-title");
  var searchUrl = document.getElementById("search-url");
  var searchDesc = document.getElementById("search-desc");

  function uid() {
    return "w" + Math.random().toString(36).slice(2, 10);
  }

  function blank(type) {
    if (type === "heading") return { id: uid(), type: "heading", props: { text: "Heading", level: 2, align: "left", tone: "default" } };
    if (type === "text") return { id: uid(), type: "text", props: { text: "Write the paragraph.", align: "left", tone: "default" } };
    if (type === "image") return { id: uid(), type: "image", props: { media_id: 0, alt: "", align: "left" } };
    if (type === "button") return { id: uid(), type: "button", props: { label: "Learn more", href: "/", align: "left" } };
    if (type === "list") return { id: uid(), type: "list", props: { items: ["First point"], ordered: false, align: "left" } };
    if (type === "spacer") return { id: uid(), type: "spacer", props: { size: "medium" } };
    if (type === "form") return { id: uid(), type: "form", props: { intro: "Send a note to the site.", form_slug: "contact", align: "left" } };
    return { id: uid(), type: "columns", props: {}, left: [], right: [] };
  }

  function snapshot() {
    history.push(JSON.stringify(doc));
    if (history.length > 40) history.shift();
    future = [];
    syncHistory();
  }

  function restore(raw) {
    doc = JSON.parse(raw);
    if (selected && !locate(selected)) selected = null;
    draw();
  }

  function syncHistory() {
    var undo = document.getElementById("editor-undo");
    var redo = document.getElementById("editor-redo");
    if (undo) undo.disabled = history.length === 0;
    if (redo) redo.disabled = future.length === 0;
  }

  function persist() {
    blocks.value = JSON.stringify(doc);
  }

  function locate(id, list) {
    var nodes = list || doc.content;
    for (var i = 0; i < nodes.length; i++) {
      if (nodes[i].id === id) return { list: nodes, index: i };
      if (nodes[i].type === "columns") {
        var left = locate(id, nodes[i].left || []);
        if (left) return left;
        var right = locate(id, nodes[i].right || []);
        if (right) return right;
      }
    }
    return null;
  }

  function nodeById(id) {
    var found = locate(id);
    return found ? found.list[found.index] : null;
  }

  function contains(id, list) {
    for (var i = 0; i < list.length; i++) {
      if (list[i].id === id) return true;
      if (list[i].type === "columns" && (contains(id, list[i].left || []) || contains(id, list[i].right || []))) return true;
    }
    return false;
  }

  function removeNode(id) {
    var found = locate(id);
    if (!found) return null;
    return found.list.splice(found.index, 1)[0];
  }

  function drawStage() {
    persist();
    stage.replaceChildren();
    if (!doc.content.length) {
      var empty = document.createElement("p");
      empty.className = "muted";
      empty.textContent = "Drag a part here, or click a part on the left.";
      stage.appendChild(empty);
    }
    doc.content.forEach(function (node, index) {
      stage.appendChild(renderNode(node, doc.content, index));
    });
  }

  function draw() {
    drawStage();
    drawInspector();
    drawSearch();
  }

  function renderNode(node, list, index) {
    var card = document.createElement("article");
    card.className = "widget" + (node.id === selected ? " selected" : "");
    card.draggable = true;
    card.appendChild(renderPreview(node));
    var tools = document.createElement("div");
    tools.className = "widget-tools";
    tools.appendChild(tool("Up", function () { move(list, index, -1); }));
    tools.appendChild(tool("Down", function () { move(list, index, 1); }));
    tools.appendChild(tool("Remove", function () { snapshot(); list.splice(index, 1); if (selected === node.id) selected = null; draw(); }));
    card.appendChild(tools);
    card.addEventListener("click", function (event) {
      event.stopPropagation();
      selected = node.id;
      draw();
    });
    card.addEventListener("dragstart", function (event) {
      dragging = { id: node.id };
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", node.id);
      event.stopPropagation();
    });
    card.addEventListener("dragover", function (event) {
      if (!dragging) return;
      event.preventDefault();
      event.stopPropagation();
      card.classList.add("over");
    });
    card.addEventListener("dragleave", function () { card.classList.remove("over"); });
    card.addEventListener("drop", function (event) {
      event.preventDefault();
      event.stopPropagation();
      card.classList.remove("over");
      insertAt(list, index);
    });
    return card;
  }

  function renderPreview(node) {
    var wrap = document.createElement("div");
    var props = node.props || {};
    if (node.type === "heading") {
      var heading = document.createElement(props.level === 3 ? "h3" : "h2");
      heading.textContent = props.text || "Heading";
      wrap.appendChild(heading);
    } else if (node.type === "text") {
      var paragraph = document.createElement("p");
      paragraph.textContent = props.text || "";
      wrap.appendChild(paragraph);
    } else if (node.type === "image") {
      var found = images.filter(function (image) { return image.id === props.media_id; })[0];
      if (!found) {
        var missing = document.createElement("p");
        missing.className = "muted";
        missing.textContent = "Add a picture from the right.";
        wrap.appendChild(missing);
      } else {
        var img = document.createElement("img");
        img.src = "/media/" + found.id;
        img.alt = props.alt || "";
        wrap.appendChild(img);
      }
    } else if (node.type === "button") {
      var link = document.createElement("span");
      link.className = "studio-link";
      link.textContent = props.label || "Button";
      wrap.appendChild(link);
    } else if (node.type === "list") {
      var list = document.createElement(props.ordered ? "ol" : "ul");
      (props.items || ["First point"]).forEach(function (item) {
        var li = document.createElement("li");
        li.textContent = item;
        list.appendChild(li);
      });
      wrap.appendChild(list);
    } else if (node.type === "spacer") {
      var gap = document.createElement("p");
      gap.className = "muted";
      gap.textContent = "Space (" + (props.size || "medium") + ")";
      wrap.appendChild(gap);
    } else if (node.type === "form") {
      var intro = document.createElement("p");
      intro.textContent = props.intro || "Contact form";
      var note = document.createElement("p");
      note.className = "muted";
      note.textContent = "Visitors open the site's contact form.";
      wrap.appendChild(intro);
      wrap.appendChild(note);
    } else if (node.type === "html") {
      var kept = document.createElement("p");
      kept.className = "muted";
      kept.textContent = "Existing page content stays when you publish. Remove this part to replace it.";
      wrap.appendChild(kept);
    } else if (node.type === "columns") {
      var slots = document.createElement("div");
      slots.className = "slots";
      slots.appendChild(slot(node, "left", "Left"));
      slots.appendChild(slot(node, "right", "Right"));
      wrap.appendChild(slots);
    }
    return wrap;
  }

  function slot(node, side, label) {
    var box = document.createElement("div");
    box.className = "slot";
    var name = document.createElement("p");
    name.className = "muted";
    name.textContent = label;
    box.appendChild(name);
    var children = node[side] || [];
    children.forEach(function (child, index) {
      box.appendChild(renderNode(child, children, index));
    });
    box.addEventListener("dragover", function (event) {
      if (!dragging) return;
      event.preventDefault();
      box.classList.add("over");
    });
    box.addEventListener("dragleave", function () { box.classList.remove("over"); });
    box.addEventListener("drop", function (event) {
      event.preventDefault();
      event.stopPropagation();
      box.classList.remove("over");
      insertAt(children, children.length);
    });
    return box;
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

  function move(list, index, step) {
    var next = index + step;
    if (next < 0 || next >= list.length) return;
    snapshot();
    var hold = list[index];
    list[index] = list[next];
    list[next] = hold;
    draw();
  }

  function insertAt(list, index) {
    if (!dragging) return;
    if (dragging.id && contains(dragging.id, list) && nodeById(dragging.id) && nodeById(dragging.id).type === "columns") {
      /* allow reorder inside the same list below */
    }
    var incoming = null;
    if (dragging.id) {
      var current = nodeById(dragging.id);
      if (!current) { dragging = null; return; }
      if (current.type === "columns" && list !== doc.content && !doc.content.includes(list)) {
        dragging = null;
        return;
      }
      if (current.type === "columns" && (list === current.left || list === current.right)) {
        dragging = null;
        return;
      }
      var from = locate(dragging.id);
      snapshot();
      incoming = removeNode(dragging.id);
      if (from && from.list === list && from.index < index) index -= 1;
    } else if (dragging.type) {
      if (dragging.type === "columns" && list !== doc.content) { dragging = null; return; }
      snapshot();
      incoming = blank(dragging.type);
    }
    dragging = null;
    if (!incoming) return;
    var at = Math.max(0, Math.min(index, list.length));
    list.splice(at, 0, incoming);
    selected = incoming.id;
    draw();
  }

  function drawInspector() {
    fields.replaceChildren();
    var node = selected ? nodeById(selected) : null;
    if (!node) {
      var hint = document.createElement("p");
      hint.className = "muted";
      hint.textContent = "Select a part on the page. Search sets the title Google shows.";
      fields.appendChild(hint);
      return;
    }
    var props = node.props || {};
    var heading = document.createElement("h2");
    heading.textContent = labelFor(node.type);
    fields.appendChild(heading);
    if (node.type === "heading") {
      fields.appendChild(field("Heading", input(props.text, function (value) { props.text = value; drawStage(); })));
      fields.appendChild(field("Size", select([["2", "Large"], ["3", "Medium"]], String(props.level || 2), function (value) { props.level = Number(value); draw(); })));
    } else if (node.type === "text") {
      fields.appendChild(field("Paragraph", area(props.text, function (value) { props.text = value; drawStage(); })));
    } else if (node.type === "image") {
      var options = [["0", "Choose a picture"]].concat(images.map(function (image) { return [String(image.id), image.name]; }));
      fields.appendChild(field("Picture", select(options, String(props.media_id || 0), function (value) { props.media_id = Number(value); draw(); })));
      fields.appendChild(uploadControl(props));
      fields.appendChild(field("Description", input(props.alt, function (value) { props.alt = value; drawStage(); })));
      var altHelp = document.createElement("p");
      altHelp.className = "muted";
      altHelp.textContent = "Describe the picture for someone who cannot see it.";
      fields.appendChild(altHelp);
    } else if (node.type === "button") {
      fields.appendChild(field("Label", input(props.label, function (value) { props.label = value; drawStage(); })));
      fields.appendChild(field("Link", input(props.href, function (value) { props.href = value; drawStage(); })));
      var linkHelp = document.createElement("p");
      linkHelp.className = "muted";
      linkHelp.textContent = "Use /about for a page on this site, or a full https address.";
      fields.appendChild(linkHelp);
    } else if (node.type === "list") {
      fields.appendChild(field("One point per line", area((props.items || []).join("\n"), function (value) { props.items = value.split("\n"); drawStage(); })));
      fields.appendChild(check("Numbered", props.ordered === true, function (value) { props.ordered = value; draw(); }));
    } else if (node.type === "spacer") {
      fields.appendChild(field("Size", select([["small", "Small"], ["medium", "Medium"], ["large", "Large"]], props.size || "medium", function (value) { props.size = value; draw(); })));
    } else if (node.type === "form") {
      fields.appendChild(field("Introduction", input(props.intro, function (value) { props.intro = value; drawStage(); })));
      fields.appendChild(field("Form address", input(props.form_slug, function (value) { props.form_slug = value; drawStage(); })));
      var formHelp = document.createElement("p");
      formHelp.className = "muted";
      formHelp.textContent = "The published page links to that form. Turn on Forms and keep a form at this address.";
      fields.appendChild(formHelp);
    } else if (node.type === "html") {
      var htmlHelp = document.createElement("p");
      htmlHelp.className = "muted";
      htmlHelp.textContent = "This is content saved before the page editor. New parts you add are published with it. Remove it when you no longer want it.";
      fields.appendChild(htmlHelp);
    } else {
      var columnsHelp = document.createElement("p");
      columnsHelp.className = "muted";
      columnsHelp.textContent = "Drag parts into the left and right sides.";
      fields.appendChild(columnsHelp);
    }
    if (node.type !== "spacer" && node.type !== "columns" && node.type !== "html" && node.type !== "image") {
      /* style tab fills the same pane when selected */
    }
    if (document.querySelector("[data-tab].on") && document.querySelector("[data-tab].on").getAttribute("data-tab") === "style") {
      fields.replaceChildren();
      var styleTitle = document.createElement("h2");
      styleTitle.textContent = "Style";
      fields.appendChild(styleTitle);
      if (node.type === "spacer") {
        fields.appendChild(field("Size", select([["small", "Small"], ["medium", "Medium"], ["large", "Large"]], props.size || "medium", function (value) { props.size = value; draw(); })));
      } else if (node.type === "columns" || node.type === "html") {
        var none = document.createElement("p");
        none.className = "muted";
        none.textContent = "This part uses the site's colors.";
        fields.appendChild(none);
      } else {
        fields.appendChild(field("Align", select([["left", "Left"], ["center", "Center"], ["right", "Right"]], props.align || "left", function (value) { props.align = value; draw(); })));
        if (node.type === "heading" || node.type === "text") {
          fields.appendChild(field("Color", select([["default", "Site text"], ["accent", "Accent"]], props.tone || "default", function (value) { props.tone = value; draw(); })));
        }
      }
    }
  }

  function labelFor(type) {
    return { heading: "Heading", text: "Text", image: "Image", button: "Button", list: "List", columns: "Columns", spacer: "Spacer", form: "Form", html: "Existing content" }[type] || "Part";
  }

  function field(label, control) {
    var wrap = document.createElement("label");
    wrap.textContent = label;
    wrap.appendChild(control);
    return wrap;
  }

  function input(value, oninput) {
    var node = document.createElement("input");
    node.value = value || "";
    node.addEventListener("input", function () { oninput(node.value); });
    return node;
  }

  function area(value, oninput) {
    var node = document.createElement("textarea");
    node.value = value || "";
    node.addEventListener("input", function () { oninput(node.value); });
    return node;
  }

  function select(options, value, onchange) {
    var node = document.createElement("select");
    options.forEach(function (pair) {
      var option = document.createElement("option");
      option.value = pair[0];
      option.textContent = pair[1];
      if (pair[0] === value) option.selected = true;
      node.appendChild(option);
    });
    node.addEventListener("change", function () { onchange(node.value); });
    return node;
  }

  function check(label, checked, onchange) {
    var box = document.createElement("input");
    box.type = "checkbox";
    box.checked = checked;
    box.addEventListener("change", function () { onchange(box.checked); });
    var wrap = document.createElement("label");
    wrap.className = "check";
    wrap.appendChild(box);
    wrap.appendChild(document.createTextNode(" " + label));
    return wrap;
  }

  function uploadControl(props) {
    var wrap = document.createElement("div");
    var file = document.createElement("input");
    file.type = "file";
    file.accept = "image/png,image/jpeg,image/gif,image/webp";
    var status = document.createElement("p");
    status.className = "muted";
    status.textContent = "Upload a PNG, JPEG, GIF, or WebP.";
    file.addEventListener("change", function () {
      if (!file.files || !file.files[0]) return;
      var body = new FormData();
      body.append("csrf", form.querySelector('input[name="csrf"]').value);
      body.append("upload", file.files[0]);
      status.textContent = "Uploading…";
      fetch(initial.uploadUrl, { method: "POST", body: body, headers: { Accept: "application/json" } })
        .then(function (response) { return response.json().then(function (payload) { return { ok: response.ok, payload: payload }; }); })
        .then(function (result) {
          if (!result.ok) {
            status.textContent = result.payload.detail || "The picture was not uploaded.";
            return;
          }
          images.push({ id: result.payload.id, name: result.payload.name });
          snapshot();
          props.media_id = result.payload.id;
          status.textContent = "Uploaded.";
          draw();
        })
        .catch(function () { status.textContent = "The picture was not uploaded."; });
    });
    wrap.appendChild(file);
    wrap.appendChild(status);
    return wrap;
  }

  function drawSearch() {
    var pageTitle = (title && title.value.trim()) || "Page title";
    var address = (slug && slug.value.trim()) || "address";
    searchTitle.textContent = pageTitle;
    searchUrl.textContent = (initial.publicPath || "") + (address === "home" ? "" : "/" + address);
    searchDesc.textContent = (description && description.value.trim()) || "The short description people see under the title.";
  }

  function showTab(name) {
    root.querySelectorAll("[data-tab]").forEach(function (button) {
      button.classList.toggle("on", button.getAttribute("data-tab") === name);
      button.setAttribute("aria-pressed", button.getAttribute("data-tab") === name ? "true" : "false");
    });
    var styleOrContent = name !== "search";
    fields.hidden = !styleOrContent;
    search.hidden = styleOrContent;
    if (styleOrContent) drawInspector();
  }

  root.querySelectorAll("[data-add]").forEach(function (button) {
    button.addEventListener("click", function () {
      if (suppressClick) { suppressClick = false; return; }
      var type = button.getAttribute("data-add");
      if (type === "columns") {
        snapshot();
        var created = blank(type);
        doc.content.push(created);
        selected = created.id;
        draw();
        return;
      }
      var target = doc.content;
      var parent = selected ? nodeById(selected) : null;
      if (parent && parent.type === "columns") target = parent.left;
      snapshot();
      var created = blank(type);
      target.push(created);
      selected = created.id;
      draw();
    });
    button.addEventListener("dragstart", function (event) {
      suppressClick = true;
      dragging = { type: button.getAttribute("data-add") };
      event.dataTransfer.effectAllowed = "copy";
      event.dataTransfer.setData("text/plain", dragging.type);
    });
  });

  stage.addEventListener("dragover", function (event) {
    if (!dragging) return;
    event.preventDefault();
    stage.classList.add("over");
  });
  stage.addEventListener("dragleave", function () { stage.classList.remove("over"); });
  stage.addEventListener("drop", function (event) {
    if (event.target.closest && (event.target.closest(".widget") || event.target.closest(".slot"))) return;
    event.preventDefault();
    stage.classList.remove("over");
    insertAt(doc.content, doc.content.length);
  });
  document.addEventListener("dragend", function () { dragging = null; });

  root.querySelectorAll("[data-tab]").forEach(function (button) {
    button.addEventListener("click", function () { showTab(button.getAttribute("data-tab")); });
  });
  document.getElementById("editor-undo").addEventListener("click", function () {
    if (!history.length) return;
    future.push(JSON.stringify(doc));
    restore(history.pop());
    syncHistory();
  });
  document.getElementById("editor-redo").addEventListener("click", function () {
    if (!future.length) return;
    history.push(JSON.stringify(doc));
    restore(future.pop());
    syncHistory();
  });
  document.getElementById("editor-desktop").addEventListener("click", function () {
    phone = false;
    frame.classList.remove("phone");
    this.setAttribute("aria-pressed", "true");
    document.getElementById("editor-phone").setAttribute("aria-pressed", "false");
  });
  document.getElementById("editor-phone").addEventListener("click", function () {
    phone = true;
    frame.classList.add("phone");
    this.setAttribute("aria-pressed", "true");
    document.getElementById("editor-desktop").setAttribute("aria-pressed", "false");
  });
  [title, slug, description].forEach(function (input) {
    if (input) input.addEventListener("input", drawSearch);
  });
  var keywords = document.getElementById("keywords");
  if (keywords) keywords.addEventListener("input", drawSearch);
  form.addEventListener("submit", persist);
  showTab("content");
  syncHistory();
  draw();
})();
