(function () {
  var form = document.getElementById("page-form");
  var initial = JSON.parse(document.getElementById("editor-initial").textContent);
  var htmlField = document.getElementById("design-html");
  var cssField = document.getElementById("design-css");
  var title = document.getElementById("title");
  var slug = document.getElementById("slug");
  var description = document.getElementById("description");
  var keywords = document.getElementById("keywords");
  var status = document.getElementById("upload-status");
  var colors = initial.colors || {};
  var accent = colors.accent || "#8c3d2f";
  var header = colors.header || "#24352c";
  var ink = colors.text || "#241f1a";
  var paper = colors.paper || "#fbf6ee";
  var editor = null;

  function keywordSlug(value) {
    return String(value || "")
      .normalize("NFKD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 80);
  }

  function publicUrl() {
    var host = String(initial.domain || "").replace(/^https?:\/\//, "").split("/")[0];
    var address = slug.value.trim() || "keyword-address";
    var path = address === "home" ? "/" : "/" + keywordSlug(address);
    if (!host) {
      return "https://your-domain" + path;
    }
    return "https://" + host + path;
  }

  function paintSearch() {
    var url = publicUrl();
    document.getElementById("search-title").textContent = title.value || "Page title";
    document.getElementById("search-url").textContent = url;
    document.getElementById("search-desc").textContent = description.value || "The description shown under the title.";
    document.getElementById("public-url").textContent = url;
    var titleLength = title.value.length;
    document.getElementById("title-count").textContent = titleLength + " characters. A search title is usually under 60.";
    var descriptionLength = description.value.length;
    document.getElementById("description-count").textContent =
      descriptionLength + " characters. The line under a search result is usually under 160.";
  }

  title.addEventListener("input", function () {
    if (!slug.readOnly && slug.dataset.touched !== "yes" && !slug.value) {
      slug.value = keywordSlug(title.value);
    }
    paintSearch();
  });
  slug.addEventListener("input", function () {
    slug.dataset.touched = "yes";
    paintSearch();
  });
  description.addEventListener("input", paintSearch);
  var useKeywords = document.getElementById("use-keywords");
  if (useKeywords) {
    useKeywords.addEventListener("click", function () {
      var next = keywordSlug(keywords.value || title.value);
      if (next) {
        slug.value = next;
        slug.dataset.touched = "yes";
        paintSearch();
      }
    });
  }
  paintSearch();

  function section(inner) {
    return '<section style="padding:56px 28px;background:' + paper + ';color:' + ink + '">' + inner + "</section>";
  }

  var editorOptions = {
    container: "#gjs",
    height: "680px",
    width: "auto",
    storageManager: false,
    noticeOnUnload: false,
    fromElement: false,
    jsInHtml: false,
    cssIcons: "",
    components: htmlField.value,
    style: cssField.value,
    canvas: { styles: ["/static/site.css"] },
    parser: { optionsHtml: { allowScripts: false, allowUnsafeAttr: false } },
    assetManager: {
      autoAdd: true,
      uploadFile: function (event) {
        var list = event.dataTransfer ? event.dataTransfer.files : event.target.files;
        if (!list || !list.length) {
          return;
        }
        Array.prototype.forEach.call(list, function (file) {
          var body = new FormData();
          body.append("csrf", form.querySelector('input[name="csrf"]').value);
          body.append("upload", file);
          status.textContent = "Uploading " + file.name + "…";
          fetch(initial.uploadUrl, { method: "POST", body: body, credentials: "same-origin" })
            .then(function (response) {
              return response.json().then(function (payload) {
                return { ok: response.ok, payload: payload };
              });
            })
            .then(function (result) {
              if (!result.ok || !result.payload.url) {
                status.textContent = (result.payload && result.payload.detail) || "The picture was not uploaded.";
                return;
              }
              editor.AssetManager.add({ src: result.payload.url, name: result.payload.name });
              var selected = editor.getSelected();
              if (selected && selected.is("image")) {
                selected.addAttributes({ src: result.payload.url, alt: selected.getAttributes().alt || result.payload.name });
              }
              status.textContent = "Picture added. Describe it in the image settings so search engines can read it.";
            })
            .catch(function () {
              status.textContent = "The picture was not uploaded.";
            });
        });
      },
    },
  };

  editor = grapesjs.init(editorOptions);
  var blocks = editor.BlockManager;
  blocks.add("hero", {
    label: "Hero",
    category: "Sections",
    content: section(
      '<h2 style="font-size:44px;line-height:1.1;margin:0 0 12px;text-align:center">A clear headline</h2>' +
        '<p style="font-size:18px;text-align:center;max-width:640px;margin:0 auto 20px">One sentence that says who this is for and what they get.</p>' +
        '<p style="text-align:center"><a href="/contact" style="display:inline-block;padding:12px 22px;border-radius:999px;background:' +
        header +
        ';color:#fff;text-decoration:none">Call to action</a></p>'
    ),
  });
  blocks.add("text", {
    label: "Text",
    category: "Sections",
    content: section("<h2>Section heading</h2><p>Write the paragraph here. Short sentences are easier to read and easier to find.</p>"),
  });
  blocks.add("image", {
    label: "Image",
    category: "Sections",
    content: section('<p style="text-align:center"><img alt="Describe this picture" style="max-width:100%;height:auto"></p>'),
  });
  blocks.add("button", {
    label: "Button",
    category: "Sections",
    content: section(
      '<p style="text-align:center"><a href="/contact" style="display:inline-block;padding:12px 22px;border-radius:999px;background:' +
        accent +
        ';color:#fff;text-decoration:none">Continue</a></p>'
    ),
  });
  blocks.add("columns", {
    label: "Columns",
    category: "Sections",
    content: section(
      '<div style="display:flex;gap:24px;flex-wrap:wrap">' +
        '<div style="flex:1;min-width:220px"><h2>First point</h2><p>Explain the first idea.</p></div>' +
        '<div style="flex:1;min-width:220px"><h2>Second point</h2><p>Explain the second idea.</p></div>' +
        "</div>"
    ),
  });
  blocks.add("features", {
    label: "Features",
    category: "Sections",
    content: section(
      '<h2 style="text-align:center">What is included</h2>' +
        '<div style="display:flex;gap:18px;flex-wrap:wrap">' +
        '<div style="flex:1;min-width:180px;padding:16px;border-radius:16px;background:#fff"><h3>One</h3><p>A short benefit.</p></div>' +
        '<div style="flex:1;min-width:180px;padding:16px;border-radius:16px;background:#fff"><h3>Two</h3><p>A short benefit.</p></div>' +
        '<div style="flex:1;min-width:180px;padding:16px;border-radius:16px;background:#fff"><h3>Three</h3><p>A short benefit.</p></div>' +
        "</div>"
    ),
  });
  blocks.add("call", {
    label: "Call to action",
    category: "Sections",
    content:
      '<section style="padding:48px 28px;background:' +
      header +
      ';color:#fff;text-align:center"><h2 style="color:#fff">Ready to talk?</h2><p>Tell people what happens when they continue.</p><p><a href="/contact" style="display:inline-block;padding:12px 22px;border-radius:999px;background:#fff;color:' +
      ink +
      ';text-decoration:none">Contact</a></p></section>',
  });

  form.addEventListener("submit", function () {
    if (!editor) {
      return;
    }
    htmlField.value = editor.getHtml();
    cssField.value = editor.getCss();
  });
})();
