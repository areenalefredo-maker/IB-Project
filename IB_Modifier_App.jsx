import { useState, useRef, useCallback } from "react";

const SUBSTITUTIONS = {
  "\\bstudent\\b": "candidate",
  "\\bstudents\\b": "candidates",
  "\\bpupil\\b": "candidate",
  "\\bpupils\\b": "candidates",
  "\\binvestigate\\b": "examine",
  "\\binvestigates\\b": "examines",
  "\\binvestigated\\b": "examined",
  "\\binvestigating\\b": "examining",
  "\\bexplore\\b": "examine",
  "\\bexplores\\b": "examines",
  "\\bexplored\\b": "examined",
  "\\bexploring\\b": "examining",
  "\\bdetermine\\b": "calculate",
  "\\bdetermines\\b": "calculates",
  "\\bdetermined\\b": "calculated",
  "\\bdetermining\\b": "calculating",
  "\\bcontainer\\b": "vessel",
  "\\bcontainers\\b": "vessels",
  "\\btablet\\b": "medicine tablet",
  "\\btablets\\b": "medicine tablets",
  "\\bshow that\\b": "demonstrate that",
  "\\boutline\\b": "summarise",
  "\\boutlines\\b": "summarises",
  "\\boutlined\\b": "summarised",
  "\\boutlining\\b": "summarising",
  "\\buse\\b": "utilise",
  "\\buses\\b": "utilises",
  "\\bused\\b": "utilised",
  "\\busing\\b": "utilising",
};

function SubBadge({ original, replacement }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "4px 10px", background: "#f0f7ff", border: "1px solid #c5ddf9", borderRadius: 20, fontSize: 13, color: "#1a3a5c" }}>
      <span style={{ fontFamily: "monospace", color: "#c0392b" }}>{original.replace(/\\b/g, "")}</span>
      <span style={{ color: "#999" }}>→</span>
      <span style={{ fontFamily: "monospace", color: "#1a7a2e" }}>{replacement}</span>
    </div>
  );
}

function FileZone({ label, file, onFile, accent }) {
  const [drag, setDrag] = useState(false);
  const inputRef = useRef();

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    setDrag(false);
    const f = e.dataTransfer.files[0];
    if (f && f.type === "application/pdf") onFile(f);
  }, [onFile]);

  return (
    <div
      onClick={() => inputRef.current.click()}
      onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
      onDragLeave={() => setDrag(false)}
      onDrop={handleDrop}
      style={{
        flex: 1, minHeight: 130, border: `2px dashed ${drag ? accent : file ? accent : "#ccd5de"}`,
        borderRadius: 14, display: "flex", flexDirection: "column", alignItems: "center",
        justifyContent: "center", cursor: "pointer", gap: 8, padding: 16, transition: "all 0.2s",
        background: drag ? `${accent}0d` : file ? `${accent}07` : "#fafbfc",
      }}
    >
      <input ref={inputRef} type="file" accept=".pdf" style={{ display: "none" }}
        onChange={e => e.target.files[0] && onFile(e.target.files[0])} />
      <div style={{ fontSize: 32 }}>{file ? "✅" : "📄"}</div>
      <div style={{ fontWeight: 700, color: "#1a2940", fontSize: 15 }}>{label}</div>
      {file
        ? <div style={{ fontSize: 12, color: "#555", maxWidth: 180, textAlign: "center", wordBreak: "break-all" }}>{file.name}</div>
        : <div style={{ fontSize: 12, color: "#999" }}>Click or drag PDF here</div>
      }
    </div>
  );
}

function ChangeRow({ ch, idx }) {
  return (
    <tr style={{ background: idx % 2 === 0 ? "#f8fafc" : "#fff" }}>
      <td style={{ padding: "6px 12px", color: "#666", fontSize: 13 }}>p.{ch.page}</td>
      <td style={{ padding: "6px 12px", fontFamily: "monospace", fontSize: 13, color: "#c0392b", maxWidth: 220, wordBreak: "break-word" }}>{ch.original}</td>
      <td style={{ padding: "6px 4px", color: "#aaa", fontSize: 13 }}>→</td>
      <td style={{ padding: "6px 12px", fontFamily: "monospace", fontSize: 13, color: "#1a7a2e", maxWidth: 220, wordBreak: "break-word" }}>{ch.modified}</td>
    </tr>
  );
}

export default function IBModifier() {
  const [qpFile, setQpFile] = useState(null);
  const [msFile, setMsFile] = useState(null);
  const [status, setStatus] = useState("idle"); // idle | loading | done | error
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [activeTab, setActiveTab] = useState("qp");

  const readFileBase64 = (file) => new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result.split(",")[1]);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });

  const buildPrompt = (type, filename) => `You are an IB exam modifier. Your task is to apply ONLY minimal linguistic substitutions (5-10% of text max) to the following IB ${type === "qp" ? "Question Paper" : "Mark Scheme"} content extracted from a PDF named "${filename}".

STRICT RULES:
1. ONLY change these specific words (and only when they appear as plain descriptive words, NOT inside equations, formulas, labels, or numbers):
   - student/students → candidate/candidates
   - investigate/investigates/investigated/investigating → examine/examines/examined/examining
   - explore/explores/explored/exploring → examine/examines/examined/examining
   - determine/determines/determined/determining → calculate/calculates/calculated/calculating
   - container/containers → vessel/vessels
   - tablet/tablets → medicine tablet/medicine tablets
   - show that → demonstrate that
   - outline/outlines/outlined/outlining → summarise/summarises/summarised/summarising
   - use/uses/used/using → utilise/utilises/utilised/utilising
   ${type === "ms" ? "- For Mark Scheme: ONLY change the above in question stems/instructions, NOT in solutions, calculations, or mark allocations." : ""}

2. NEVER change: equations, formulas, numbers, units, chemical symbols, ion notation, table data, diagram labels, answers, marks, page numbers, headers, footers.

3. Preserve all formatting indicators in the text (newlines, spaces, punctuation).

4. Respond ONLY with a JSON object in this exact format:
{
  "changes": [
    {"page": <page_number_if_known_else_1>, "original": "<original phrase>", "modified": "<new phrase>", "context": "<short surrounding sentence fragment>"}
  ],
  "modification_rate_estimate": "<X%>",
  "summary": "<one sentence summary of changes made>"
}

If NO safe changes can be made, return: {"changes": [], "modification_rate_estimate": "0%", "summary": "No safe linguistic substitutions found."}

Here is the extracted text content from the PDF (pages separated by === PAGE N ===):`;

  const handleProcess = async () => {
    if (!qpFile && !msFile) return;
    setStatus("loading");
    setError("");
    setResult(null);

    try {
      const results = {};

      for (const [key, file] of [["qp", qpFile], ["ms", msFile]]) {
        if (!file) continue;

        const base64 = await readFileBase64(file);
        const prompt = buildPrompt(key, file.name);

        const response = await fetch("https://api.anthropic.com/v1/messages", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            model: "claude-sonnet-4-20250514",
            max_tokens: 1000,
            messages: [{
              role: "user",
              content: [
                {
                  type: "document",
                  source: { type: "base64", media_type: "application/pdf", data: base64 }
                },
                { type: "text", text: prompt }
              ]
            }]
          })
        });

        const data = await response.json();
        if (data.error) throw new Error(data.error.message);

        const text = data.content.map(i => i.text || "").join("\n");
        const clean = text.replace(/```json|```/g, "").trim();
        let parsed;
        try {
          parsed = JSON.parse(clean);
        } catch {
          // Try to extract JSON from text
          const match = clean.match(/\{[\s\S]*\}/);
          parsed = match ? JSON.parse(match[0]) : { changes: [], modification_rate_estimate: "0%", summary: "Could not parse response." };
        }

        results[key] = { ...parsed, filename: file.name };
      }

      setResult(results);
      setStatus("done");
    } catch (e) {
      setError(e.message || "Processing failed");
      setStatus("error");
    }
  };

  const canProcess = (qpFile || msFile) && status !== "loading";
  const hasResult = status === "done" && result;

  return (
    <div style={{ minHeight: "100vh", background: "linear-gradient(135deg, #0d1b2a 0%, #1b3a5c 50%, #0d1b2a 100%)", padding: "32px 16px", fontFamily: "'Segoe UI', system-ui, sans-serif" }}>
      {/* Header */}
      <div style={{ maxWidth: 800, margin: "0 auto 28px", textAlign: "center" }}>
        <div style={{ display: "inline-flex", alignItems: "center", gap: 10, background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.12)", borderRadius: 40, padding: "6px 18px", marginBottom: 16 }}>
          <span style={{ fontSize: 18 }}>📝</span>
          <span style={{ color: "#a8c8f0", fontSize: 13, fontWeight: 600, letterSpacing: 1.5, textTransform: "uppercase" }}>IB Exam Modifier</span>
        </div>
        <h1 style={{ color: "#e8f4ff", fontSize: 30, fontWeight: 800, margin: "0 0 8px", letterSpacing: -0.5 }}>
          Minimal Linguistic Modification
        </h1>
        <p style={{ color: "#7aaed4", fontSize: 15, margin: 0 }}>
          5–10% text substitution only · Zero layout change · 100% format preservation
        </p>
      </div>

      <div style={{ maxWidth: 800, margin: "0 auto", display: "flex", flexDirection: "column", gap: 20 }}>

        {/* Upload Zone */}
        <div style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.10)", borderRadius: 18, padding: 24 }}>
          <div style={{ color: "#c0d9f0", fontWeight: 700, fontSize: 14, marginBottom: 14, letterSpacing: 0.5 }}>UPLOAD FILES</div>
          <div style={{ display: "flex", gap: 14 }}>
            <FileZone label="Question Paper (QP)" file={qpFile} onFile={setQpFile} accent="#3b82f6" />
            <FileZone label="Mark Scheme (MS)" file={msFile} onFile={setMsFile} accent="#10b981" />
          </div>
          <button
            onClick={handleProcess}
            disabled={!canProcess}
            style={{
              marginTop: 18, width: "100%", padding: "14px", borderRadius: 12, border: "none",
              background: canProcess ? "linear-gradient(135deg, #3b82f6, #1d4ed8)" : "#2a3a4a",
              color: canProcess ? "#fff" : "#556677", fontSize: 15, fontWeight: 700, cursor: canProcess ? "pointer" : "not-allowed",
              transition: "all 0.2s", letterSpacing: 0.5,
            }}
          >
            {status === "loading" ? "⏳  Analysing PDF content…" : "⚡  Apply Modifications"}
          </button>
          {status === "error" && (
            <div style={{ marginTop: 12, padding: "10px 14px", background: "#3a1010", border: "1px solid #8b2020", borderRadius: 10, color: "#ff8888", fontSize: 13 }}>
              ❌ {error}
            </div>
          )}
        </div>

        {/* Substitution Dictionary */}
        <div style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.10)", borderRadius: 18, padding: 24 }}>
          <div style={{ color: "#c0d9f0", fontWeight: 700, fontSize: 14, marginBottom: 14, letterSpacing: 0.5 }}>SUBSTITUTION RULES</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {Object.entries(SUBSTITUTIONS).slice(0, 18).map(([k, v]) => (
              <SubBadge key={k} original={k} replacement={v} />
            ))}
          </div>
        </div>

        {/* Results */}
        {hasResult && (
          <div style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.10)", borderRadius: 18, padding: 24 }}>
            <div style={{ color: "#c0d9f0", fontWeight: 700, fontSize: 14, marginBottom: 16, letterSpacing: 0.5 }}>MODIFICATION REPORT</div>

            {/* Tabs */}
            {Object.keys(result).length > 1 && (
              <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
                {Object.keys(result).map(k => (
                  <button key={k} onClick={() => setActiveTab(k)} style={{
                    padding: "7px 18px", borderRadius: 8, border: "none",
                    background: activeTab === k ? "#3b82f6" : "rgba(255,255,255,0.07)",
                    color: activeTab === k ? "#fff" : "#99b5cc", fontWeight: 600, cursor: "pointer", fontSize: 13,
                  }}>
                    {k.toUpperCase()}
                  </button>
                ))}
              </div>
            )}

            {Object.entries(result).map(([key, data]) => (
              (Object.keys(result).length === 1 || activeTab === key) && (
                <div key={key}>
                  {/* Stats */}
                  <div style={{ display: "flex", gap: 12, marginBottom: 16, flexWrap: "wrap" }}>
                    {[
                      { label: "File", value: data.filename, icon: "📄" },
                      { label: "Changes Found", value: data.changes?.length ?? 0, icon: "✏️" },
                      { label: "Modification Rate", value: data.modification_rate_estimate, icon: "📊" },
                    ].map(s => (
                      <div key={s.label} style={{ flex: 1, minWidth: 120, background: "rgba(255,255,255,0.06)", borderRadius: 12, padding: "12px 14px" }}>
                        <div style={{ fontSize: 18, marginBottom: 4 }}>{s.icon}</div>
                        <div style={{ color: "#e8f4ff", fontWeight: 700, fontSize: 15, wordBreak: "break-word" }}>{s.value}</div>
                        <div style={{ color: "#7a9ab5", fontSize: 12 }}>{s.label}</div>
                      </div>
                    ))}
                  </div>

                  {/* Summary */}
                  {data.summary && (
                    <div style={{ padding: "10px 14px", background: "rgba(59,130,246,0.1)", border: "1px solid rgba(59,130,246,0.25)", borderRadius: 10, color: "#a8c8f0", fontSize: 14, marginBottom: 16 }}>
                      💡 {data.summary}
                    </div>
                  )}

                  {/* Change Table */}
                  {data.changes?.length > 0 ? (
                    <div style={{ overflowX: "auto", borderRadius: 10, border: "1px solid rgba(255,255,255,0.10)" }}>
                      <table style={{ width: "100%", borderCollapse: "collapse", background: "#fff" }}>
                        <thead>
                          <tr style={{ background: "#1a2940" }}>
                            {["Page", "Original", "", "Modified"].map(h => (
                              <th key={h} style={{ padding: "8px 12px", color: "#7aaed4", fontSize: 12, fontWeight: 700, textAlign: "left", letterSpacing: 0.5, textTransform: "uppercase" }}>{h}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {data.changes.map((ch, i) => <ChangeRow key={i} ch={ch} idx={i} />)}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <div style={{ padding: 20, textAlign: "center", color: "#7a9ab5", fontSize: 14 }}>
                      No safe substitutions found for this document.
                    </div>
                  )}
                </div>
              )
            ))}
          </div>
        )}

        {/* Instructions */}
        <div style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.07)", borderRadius: 18, padding: 20 }}>
          <div style={{ color: "#99b5cc", fontWeight: 700, fontSize: 13, marginBottom: 12, letterSpacing: 0.5 }}>HOW TO APPLY CHANGES TO YOUR PDF</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {[
              ["1", "Upload QP and/or MS PDF above and click Apply Modifications"],
              ["2", "Review the change report – verify all substitutions are safe"],
              ["3", "Run the Python script on your server for actual PDF output:"],
            ].map(([n, t]) => (
              <div key={n} style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
                <div style={{ width: 22, height: 22, borderRadius: "50%", background: "#1d4ed8", color: "#fff", fontSize: 12, fontWeight: 700, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, marginTop: 1 }}>{n}</div>
                <div style={{ color: "#8aadca", fontSize: 14 }}>{t}</div>
              </div>
            ))}
          </div>
          <div style={{ marginTop: 12, background: "#0a1520", borderRadius: 8, padding: "12px 14px", fontFamily: "monospace", fontSize: 13, color: "#7dd3fc", border: "1px solid #1e3a5c" }}>
            python modifier.py --qp paper1.pdf --ms markscheme.pdf --out ./output
          </div>
        </div>
      </div>
    </div>
  );
}
