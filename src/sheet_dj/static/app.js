(() => {
  "use strict";

  const STORAGE_KEY = "sheet-dj";
  const songs = document.getElementById("songs");
  const setList = document.getElementById("set-list");
  const exportForm = document.getElementById("export");
  const nameInput = exportForm.elements.name;
  const uploadForm = document.getElementById("upload");
  const fileInput = uploadForm.elements.scores;
  const button = (id) => document.getElementById(id);

  const items = (list) => Array.from(list.children).filter((el) => el.tagName === "LI");
  const selectedIn = (list) => items(list).filter((el) => el.classList.contains("selected"));
  const otherList = (list) => (list === songs ? setList : songs);
  const libraryOrder = (a, b) => Number(a.dataset.index) - Number(b.dataset.index);

  // sessionStorage can be missing or blocked; the page must work without it.
  function readStorage() {
    try {
      return JSON.parse(sessionStorage.getItem(STORAGE_KEY)) || {};
    } catch (error) {
      return {};
    }
  }

  function writeStorage() {
    try {
      sessionStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({ ids: items(setList).map((el) => el.dataset.id), name: nameInput.value }),
      );
    } catch (error) {
      /* nothing to do: the set list just will not survive a reload */
    }
  }

  function deselect(elements) {
    elements.forEach((el) => Sortable.utils.deselect(el));
  }

  function updateControls() {
    document.getElementById("songs-count").textContent = `(${items(songs).length})`;
    document.getElementById("set-list-count").textContent = `(${items(setList).length})`;
    button("add").disabled = selectedIn(songs).length === 0;
    for (const id of ["remove", "up", "down"]) button(id).disabled = selectedIn(setList).length === 0;
    button("shuffle").disabled = items(setList).length < 2;
    button("random").disabled = items(songs).length === 0;
  }

  // Songs stay in library order; the set list keeps the user's order.
  function refresh() {
    const current = items(songs);
    const sorted = current.slice().sort(libraryOrder);
    if (sorted.some((el, i) => el !== current[i])) sorted.forEach((el) => songs.appendChild(el));
    updateControls();
    writeStorage();
  }

  function move(elements, target) {
    deselect(elements); // Sortable tracks one selection; moved songs start unselected
    elements.forEach((el) => target.appendChild(el));
    refresh();
  }

  function shiftSelected(direction) {
    const chosen = selectedIn(setList);
    if (direction > 0) chosen.reverse();
    for (const el of chosen) {
      const neighbour = direction < 0 ? el.previousElementSibling : el.nextElementSibling;
      if (!neighbour || neighbour.classList.contains("selected")) continue;
      setList.insertBefore(el, direction < 0 ? neighbour : neighbour.nextElementSibling);
    }
    refresh();
  }

  function shuffle(list) {
    const shuffled = items(list);
    for (let i = shuffled.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
    }
    return shuffled;
  }

  function addRandom() {
    const wanted = Math.floor(Number(document.getElementById("random-count").value));
    if (!(wanted > 0)) return;
    move(shuffle(songs).slice(0, wanted), setList);
  }

  function selectAll(list) {
    items(list).forEach((el) => Sortable.utils.select(el));
    updateControls();
  }

  function toggleSelection(el) {
    if (el.classList.contains("selected")) Sortable.utils.deselect(el);
    else Sortable.utils.select(el);
    updateControls();
  }

  function moveAcross(el) {
    const list = el.parentElement;
    move(el.classList.contains("selected") ? selectedIn(list) : [el], otherList(list));
  }

  function makeSortable(list, sortable) {
    new Sortable(list, {
      group: "songs",
      multiDrag: true,
      multiDragKey: "Control", // a plain click selects one; Ctrl adds; Shift selects a range
      avoidImplicitDeselect: true, // so the buttons still see the selection after a click
      selectedClass: "selected",
      animation: 150,
      fallbackTolerance: 3,
      sort: sortable,
      onSelect: updateControls,
      onDeselect: updateControls,
      onEnd: refresh,
    });
  }

  function restoreSetList() {
    if (items(setList).length > 0) return; // the server sent one back after an error: keep it
    const saved = readStorage();
    for (const id of saved.ids || []) {
      const el = songs.querySelector(`[data-id="${CSS.escape(id)}"]`);
      if (el) setList.appendChild(el);
    }
    if (saved.name && nameInput.value === nameInput.dataset.default) nameInput.value = saved.name;
  }

  function fillExportForm() {
    exportForm.querySelectorAll('input[name="song"]').forEach((el) => el.remove());
    for (const el of items(setList)) {
      const input = document.createElement("input");
      input.type = "hidden";
      input.name = "song";
      input.value = el.dataset.id;
      exportForm.appendChild(input);
    }
  }

  function setUpFileDrop() {
    const hasFiles = (event) => Array.from(event.dataTransfer.types || []).includes("Files");
    document.addEventListener("dragover", (event) => {
      if (!hasFiles(event)) return;
      event.preventDefault();
      document.body.classList.add("dropping");
    });
    document.addEventListener("dragleave", (event) => {
      if (event.relatedTarget === null) document.body.classList.remove("dropping");
    });
    document.addEventListener("drop", (event) => {
      document.body.classList.remove("dropping");
      if (!hasFiles(event)) return;
      event.preventDefault();
      fileInput.files = event.dataTransfer.files;
      uploadForm.requestSubmit();
    });
  }

  // A page that came from a form post would ask to resubmit on reload: make it a plain page.
  if (location.pathname !== "/") history.replaceState(null, "", "/");

  makeSortable(songs, false);
  makeSortable(setList, true);
  restoreSetList();
  refresh();

  button("add").addEventListener("click", () => move(selectedIn(songs), setList));
  button("remove").addEventListener("click", () => move(selectedIn(setList), songs));
  button("up").addEventListener("click", () => shiftSelected(-1));
  button("down").addEventListener("click", () => shiftSelected(1));
  button("shuffle").addEventListener("click", () => {
    shuffle(setList).forEach((el) => setList.appendChild(el));
    refresh();
  });
  button("random").addEventListener("click", addRandom);
  document.querySelectorAll("[data-select-all]").forEach((el) =>
    el.addEventListener("click", () => selectAll(document.getElementById(el.dataset.selectAll))),
  );

  for (const list of [songs, setList]) {
    list.addEventListener("dblclick", (event) => {
      const el = event.target.closest("li");
      if (el) moveAcross(el);
    });
    list.addEventListener("keydown", (event) => {
      const el = event.target.closest("li");
      if (!el) return;
      if (event.key === " ") {
        event.preventDefault();
        toggleSelection(el);
      } else if (event.key === "Enter") {
        event.preventDefault();
        moveAcross(el);
      }
    });
  }

  nameInput.addEventListener("input", writeStorage);
  exportForm.addEventListener("submit", fillExportForm);
  uploadForm.addEventListener("submit", () => {
    uploadForm.querySelector("button").setAttribute("aria-busy", "true");
  });
  setUpFileDrop();
})();
