const $ = id => document.getElementById(id);

const uploadZone = $("upload-zone");
const imageInput = $("image-input");
const previewStage = $("preview-stage");
const previewImg = $("preview-img");
const form = $("project-form");
const submitBtn = $("submit-btn");
const lengthInput = $("length-input");
const widthInput = $("width-input");
const heightInput = $("height-input");
const customerInput = $("customer-input");
const processing = $("processing");
const results = $("results");
const rejection = $("reject-section");

let uploadedFile = null;
let selectedType = "1_seater";
let timers = [];

document.querySelectorAll(".sofa-type").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".sofa-type").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    selectedType = btn.dataset.type;
  });
});

["dragover","dragenter"].forEach(evt => uploadZone.addEventListener(evt, e => {
  e.preventDefault();
  uploadZone.style.background = "#ddd8cd";
}));
["dragleave","drop"].forEach(evt => uploadZone.addEventListener(evt, e => {
  e.preventDefault();
  uploadZone.style.background = "";
}));
uploadZone.addEventListener("drop", e => {
  const file = e.dataTransfer.files[0];
  if (file) setFile(file);
});
imageInput.addEventListener("change", () => {
  if (imageInput.files[0]) setFile(imageInput.files[0]);
});

function setFile(file){
  if (!file.type.startsWith("image/")) return;
  uploadedFile = file;
  previewImg.src = URL.createObjectURL(file);
  previewStage.classList.add("show");
  checkForm();
}
function checkForm(){
  submitBtn.disabled = !(uploadedFile && +lengthInput.value > 0 && +widthInput.value > 0 && +heightInput.value > 0);
}
[lengthInput,widthInput,heightInput,customerInput].forEach(el => el.addEventListener("input", checkForm));

form.addEventListener("submit", async e => {
  e.preventDefault();
  if (!uploadedFile) return;

  form.closest(".project-section").style.display = "none";
  document.querySelector(".process-section").style.display = "none";
  processing.classList.add("show");
  results.classList.remove("show");
  rejection.classList.remove("show");
  animateProcessing();

  const fd = new FormData();
  fd.append("image", uploadedFile);
  fd.append("customer_name", customerInput.value.trim() || "Guest");
  fd.append("length_mm", lengthInput.value);
  fd.append("width_mm", widthInput.value);
  fd.append("height_mm", heightInput.value);

  try {
    const resp = await fetch("/api/quote", {method:"POST", body:fd});
    const data = await resp.json();
    stopProcessing();

    if (data.status === "success") {
      renderResults(data);
      processing.classList.remove("show");
      results.classList.add("show");
      window.scrollTo({top:0, behavior:"smooth"});
    } else {
      renderRejection(data);
    }
  } catch(err){
    stopProcessing();
    renderRejection({reason:"Network error: " + err.message, sofa_analysis:{}});
  }
});

function animateProcessing(){
  const stages = [
    ["READING FORM","Extracting furniture geometry and manufacturing parameters.","18%","IMAGE INGEST"],
    ["DETECTING","Identifying sofa configuration and components.","43%","GEOMETRY DETECTION"],
    ["ENGINEERING","Scaling the bill of materials to the requested dimensions.","72%","BOM SCALING"],
    ["BUILDING OUTPUT","Preparing CAD and quotation artifacts.","96%","OUTPUT GENERATION"]
  ];
  stages.forEach((s,i)=>{
    timers.push(setTimeout(()=>{
      $("processing-title").textContent=s[0];
      $("processing-sub").textContent=s[1];
      $("progress-bar").style.width=s[2];
      $("process-status").textContent=s[3];
    }, i*900));
  });
}
function stopProcessing(){timers.forEach(clearTimeout);timers=[];$("progress-bar").style.width="100%";}

function syncDetectedSofaType(predictedType){
  if (!predictedType) return;

  const validTypes = ["1_seater", "2_seater", "3_seater", "l_shape", "4_seater_plus"];
  if (!validTypes.includes(predictedType)) return;

  selectedType = predictedType;

  document.querySelectorAll(".sofa-type").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.type === predictedType);
  });
}


function openInspectionViewer(){
  const viewer = $("inspection-viewer");
  const source = $("annotated-img");
  const target = $("inspection-viewer-img");
  if (!viewer || !source || !target || !source.src) return;

  target.src = source.src;
  $("inspection-viewer-type").textContent = $("detected-type").textContent || "SOFA";
  $("inspection-viewer-confidence").textContent = $("conf-label").textContent || "�";
  $("inspection-viewer-meta").textContent = $("detected-meta").textContent || "�";

  viewer.classList.add("is-open");
  viewer.setAttribute("aria-hidden", "false");
  document.body.style.overflow = "hidden";
}

function closeInspectionViewer(){
  const viewer = document.getElementById("inspection-viewer");
  if (!viewer) return;

  viewer.classList.remove("is-open");
  viewer.setAttribute("aria-hidden", "true");
  viewer.style.opacity = "0";
  viewer.style.visibility = "hidden";
  viewer.style.pointerEvents = "none";

  document.body.style.overflow = "";
}

const resultImageWrap = $("result-image-wrap");
if (resultImageWrap) resultImageWrap.addEventListener("click", openInspectionViewer);

const inspectionClose = $("inspection-close");
if (inspectionClose) {
  inspectionClose.addEventListener("click", function(e) {
    e.preventDefault();
    e.stopPropagation();
    closeInspectionViewer();
  });
}

const inspectionViewer = $("inspection-viewer");
if (inspectionViewer) inspectionViewer.addEventListener("click", e => {
  if (e.target === inspectionViewer) closeInspectionViewer();
});

document.addEventListener("keydown", e => {
  if (e.key === "Escape") closeInspectionViewer();
});

function renderResults(data){
  const sa = data.sofa_analysis || {};
  syncDetectedSofaType(sa.predicted_type);
  const typeMap = {
    "1_seater":"1-SEATER / ARMCHAIR",
    "2_seater":"2-SEATER",
    "3_seater":"3-SEATER",
    "l_shape":"L-SHAPE",
    "4_seater_plus":"4-SEATER+"
  };
  $("detected-type").textContent = typeMap[sa.predicted_type] || sa.predicted_type || "SOFA";
  const conf = Math.round((sa.confidence || 0)*100);
  $("conf-label").textContent = conf + "%";
  setTimeout(()=> $("conf-fill").style.width=conf+"%",150);
  $("detected-meta").textContent =
    `REQUEST ${data.request_id || "—"} · BBOX ${(sa.bbox||[]).join(", ") || "—"} · BACKEND ${sa.detector_backend || "YOLOv8"}`;

  const components = Array.isArray(sa.components) ? sa.components : [];
  let componentPanel = $("component-inspection");
  if (!componentPanel) {
    componentPanel = document.createElement("div");
    componentPanel.id = "component-inspection";
    componentPanel.className = "component-inspection";
    $("detected-meta").insertAdjacentElement("afterend", componentPanel);
  }

  const componentNames = {
    seat_cushion: "SEAT CUSHION",
    back_cushion: "BACK CUSHION",
    right_arm: "RIGHT ARM",
    left_arm: "LEFT ARM",
    armrest: "ARMREST",
    legs: "LEGS",
    frame: "FRAME",
    back_frame: "BACK FRAME"
  };

  const groupedComponents = {};
  components.forEach(c => {
    const key = c.class_name || "component";
    if (!groupedComponents[key]) groupedComponents[key] = {count:0, confidence:0};
    groupedComponents[key].count++;
    groupedComponents[key].confidence = Math.max(groupedComponents[key].confidence, Number(c.confidence || 0));
  });

  const componentEntries = Object.entries(groupedComponents);
  componentPanel.innerHTML = componentEntries.length ? `
    <div class="component-heading">
      <span>COMPONENT INSPECTION</span>
      <b>${componentEntries.length.toString().padStart(2,"0")} CLASSES</b>
    </div>
    <div class="component-list">
      ${componentEntries.map(([name, info], i) => `
        <div class="component-row">
          <span class="component-number">${String(i + 1).padStart(2,"0")}</span>
          <span class="component-name">${componentNames[name] || name.replaceAll("_"," ").toUpperCase()}</span>
          <span class="component-count">${info.count > 1 ? "�" + info.count : ""}</span>
          <span class="component-confidence">${Math.round(info.confidence * 100)}%</span>
        </div>`).join("")}
    </div>
  ` : `<div class="component-heading"><span>COMPONENT INSPECTION</span><b>NO DATA</b></div>`;

  if (data.annotated_image_url){
    $("annotated-img").src=data.annotated_image_url;
    $("result-image-wrap").classList.add("has-image");
  } else {
    $("result-image-wrap").classList.remove("has-image");
    $("result-image-wrap").style.display="flex";
    $("result-image-wrap").innerHTML='<div class="mono" style="color:#777">NO ANNOTATED PREVIEW</div>';
  }

  const d=data.dimensions_mm||{};
  $("r-length").textContent=d.length||"—";
  $("r-width").textContent=d.width||"—";
  $("r-height").textContent=d.height||"—";
  $("fp-length").textContent=d.length||"—";
  $("fp-width").textContent=d.width||"—";
  $("fp-height").textContent=d.height||"—";

  const q=data.quote||{};
  $("final-price").textContent="₹"+fmt(q.final_quotation_price);

  const tbody=$("bom-tbody");
  tbody.innerHTML=(data.bom||[]).map(row=>`
    <tr>
      <td>${esc(row.component)}</td>
      <td>${esc(row.scaling_rule)}</td>
      <td>${esc(row.qty)}</td>
      <td>₹${fmt(row.unit_cost)}</td>
      <td>₹${fmt(row.total_cost)}</td>
    </tr>`).join("") || `<tr><td colspan="5">No BOM rows returned.</td></tr>`;

  const rows=[
    ["Material",q.material_cost],["Labour",q.labor_cost],["Finishing",q.finishing_cost],
    ["Subtotal",q.subtotal],["Overhead",q.overhead],["Cost + overhead",q.cost_after_overhead],
    ["Profit",q.profit]
  ];
  $("quote-rows").innerHTML=rows.map(([k,v])=>`<div><span>${k}</span><b>₹${fmt(v)}</b></div>`).join("");

  const cad=[];
  if(data.cad_step_url) cad.push(`<a href="${data.cad_step_url}" download>STEP / 3D MODEL ↗</a>`);
  if(data.cad_dxf_url) cad.push(`<a href="${data.cad_dxf_url}" download>DXF / TECHNICAL DRAWING ↗</a>`);
  if(data.cad_preview_url) cad.push(`<a href="${data.cad_preview_url}" download>PNG / PREVIEW ↗</a>`);
  $("cad-files").innerHTML=cad.length?cad.join(""):"<span>CAD output was not generated for this request.</span>";

  const path=data.input_request_path || (data.request_id ? `outputs/requests/${data.request_id}/input_request.json` : "—");
  $("fp-path").textContent=path;
  $("fp-copy-btn").onclick=async()=>{
    try{await navigator.clipboard.writeText(path);$("fp-copy-btn").textContent="COPIED";setTimeout(()=>$("fp-copy-btn").textContent="COPY PATH",1500)}
    catch{ $("fp-copy-btn").textContent="COPY FAILED"; }
  };
}

function renderRejection(data){
  processing.classList.remove("show");
  results.classList.remove("show");
  rejection.classList.add("show");
  $("reject-title").innerHTML=(data.sofa_analysis||{}).detected_object ? "INPUT<br><em>REVIEW.</em>" : "SOFA<br><em>NOT FOUND.</em>";
  $("reject-reason").textContent=data.reason||"The request could not be processed.";
  const sa=data.sofa_analysis||{};
  $("reject-detail").innerHTML=sa.predicted_type
    ? `DETECTED: <strong>${esc(sa.predicted_type)}</strong> · CONFIDENCE: <strong>${Math.round((sa.confidence||0)*100)}%</strong>`
    : "No sofa object was detected in the supplied image.";
  window.scrollTo({top:0,behavior:"smooth"});
}

function resetProject(){
  uploadedFile=null; imageInput.value=""; previewStage.classList.remove("show");
  [lengthInput,widthInput,heightInput,customerInput].forEach(x=>x.value="");
  submitBtn.disabled=true;
  form.closest(".project-section").style.display="";
  document.querySelector(".process-section").style.display="";
  results.classList.remove("show"); rejection.classList.remove("show"); processing.classList.remove("show");
  window.scrollTo({top:0,behavior:"smooth"});
}
$("new-request-btn").addEventListener("click",resetProject);
$("retry-btn").addEventListener("click",resetProject);

function fmt(n){
  if(n===undefined||n===null||n==="") return "—";
  return Number(n).toLocaleString("en-IN",{minimumFractionDigits:2,maximumFractionDigits:2});
}
function esc(v){
  return String(v??"").replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[m]));
}

document.addEventListener("mousemove", e=>{
  document.documentElement.style.setProperty("--mx", e.clientX+"px");
  document.documentElement.style.setProperty("--my", e.clientY+"px");
});




