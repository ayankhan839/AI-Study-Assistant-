import { useRef, useState } from "react";
import { BookOpen, MessageCircle, NotebookPen, ListChecks, FileText, UploadCloud, Search, Plus, X, File, FileImage, FileType2, Menu, ArrowUpRight, Sparkles, FolderOpen, Send, Download, LoaderCircle, Trash2 } from "lucide-react";

const API = "http://127.0.0.1:8000";
const sections = [
  { id:"materials", label:"Study materials", icon:BookOpen },
  { id:"chat", label:"AI chat", icon:MessageCircle },
  { id:"notes", label:"Notes", icon:NotebookPen },
  { id:"summary", label:"Summarizer", icon:FileText },
  { id:"quiz", label:"Quiz", icon:ListChecks }
];
const initial = { level:"Simple", style:"Headings and bullet points" };
function getFileIcon(file) {
  if (file.type.startsWith("image/")) return FileImage;
  if (file.name.toLowerCase().endsWith(".pdf")) return FileType2;
  return File;
}
async function readError(response) {
  try { const data=await response.json(); return data.detail || "Request failed."; }
  catch { return "Request failed. Check that the backend is running."; }
}
export default function App() {
  const [active,setActive] = useState("materials");
  const [files,setFiles] = useState([]);
  const [material,setMaterial] = useState("");
  const [query,setQuery] = useState("");
  const [mobileMenu,setMobileMenu] = useState(false);
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState("");
  const [notice,setNotice] = useState("");
  const [level,setLevel] = useState("Simple");
  const [chatInput,setChatInput] = useState("");
  const [messages,setMessages] = useState([]);
  const [topic,setTopic] = useState("");
  const [noteStyle,setNoteStyle] = useState("Headings and bullet points");
  const [notes,setNotes] = useState("");
  const [summaryStyle,setSummaryStyle] = useState("Short summary");
  const [summary,setSummary] = useState("");
  const [quizCount,setQuizCount] = useState(30);
  const [quiz,setQuiz] = useState([]);
  const [quizTopic,setQuizTopic] = useState("");
  const [selected,setSelected] = useState({});
  const picker = useRef(null);
  const current = sections.find(item => item.id === active);
  const visibleFiles = files.filter(file => file.name.toLowerCase().includes(query.toLowerCase()));
  async function addFiles(selectedFiles) {
    const incoming = Array.from(selectedFiles || []);
    if (!incoming.length) return;
    setBusy(true); setError(""); setNotice("");
    for (const file of incoming) {
      const exists=files.some(old=>old.name===file.name && old.size===file.size);
      if (exists) continue;
      try {
        const form=new FormData(); form.append("file",file);
        const response=await fetch(API+"/api/upload",{method:"POST",body:form});
        if (!response.ok) throw new Error(await readError(response));
        const data=await response.json();
        setMaterial(old => old ? old+"\n\n"+data.text : data.text);
        setFiles(old=>[...old,{name:file.name,size:file.size,type:file.type,text:data.text,meta:data}]);
        setNotice(file.name+" uploaded and text extracted ("+data.characters.toLocaleString()+" characters).");
      } catch(e) { setError(file.name+": "+e.message); }
    }
    setBusy(false);
  }
  async function request(path,payload) {
    setBusy(true); setError(""); setNotice("");
    try {
      const response=await fetch(API+path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
      if (!response.ok) throw new Error(await readError(response));
      return await response.json();
    } catch(e) { setError(e.message || "Could not connect to backend."); return null; }
    finally { setBusy(false); }
  }
  async function sendChat(e) {
    e.preventDefault(); const question=chatInput.trim(); if(!question)return;
    const history=messages.slice(-6);
    setMessages(old=>[...old,{role:"user",content:question}]); setChatInput("");
    const data=await request("/api/chat",{material,question,level,history});
    if(data?.answer)setMessages(old=>[...old,{role:"assistant",content:data.answer}]);
  }
  async function generateNotes() {
    const data=await request("/api/notes",{material,topic,level,style:noteStyle});
    if(data?.result)setNotes(data.result);
  }
  async function generateSummary() {
    const data=await request("/api/summarize",{material,level,style:summaryStyle});
    if(data?.result)setSummary(data.result);
  }
  async function generateQuiz() {
    const data=await request("/api/quiz",{material,topic:quizTopic,level,count:quizCount});
    if(data?.questions){setQuiz(data.questions);setSelected({});}
  }
  async function downloadQuiz(includeAnswers) {
    setBusy(true);setError("");
    try {
      const response=await fetch(API+"/api/quiz/pdf",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({topic:quizTopic||"Practice Quiz",questions:quiz,include_answers:includeAnswers})});
      if(!response.ok)throw new Error(await readError(response));
      const blob=await response.blob();const url=URL.createObjectURL(blob);const a=document.createElement("a");
      a.href=url;a.download=includeAnswers?"Quiz_With_Answer_Key.pdf":"Quiz_Questions_Only.pdf";a.click();URL.revokeObjectURL(url);
    } catch(e){setError(e.message);}
    finally{setBusy(false);}
  }
  const levelControl=<label className="field-label">Language level<select value={level} onChange={e=>setLevel(e.target.value)}><option>Simple</option><option>Intermediate</option><option>Advanced</option></select></label>;
  const materialHint=material ? <p className="material-status"><span className="status-dot"/> {material.length.toLocaleString()} characters of extracted study material available to AI tools.</p> : <p className="material-status">Upload material first, or enter a topic where supported.</p>;
  return <div className="app-shell">
    <header className="topbar">
      <a className="brand" href="#" onClick={e=>e.preventDefault()}><span className="brand-mark"><BookOpen size={19}/></span><span>study<span className="brand-light">desk</span></span></a>
      <div className="topbar-note"><span className="status-dot"/> Your personal study workspace</div>
      <button className="mobile-menu-button" aria-label="Toggle navigation" onClick={()=>setMobileMenu(!mobileMenu)}><Menu size={21}/></button>
    </header>
    <div className="workspace">
      <aside className={`sidebar ${mobileMenu ? "sidebar-open" : ""}`}>
        <div className="nav-caption">WORKSPACE</div>
        <nav aria-label="Main navigation">{sections.map(item=>{const Icon=item.icon;return <button key={item.id} className={`nav-item ${active===item.id?"active":""}`} onClick={()=>{setActive(item.id);setMobileMenu(false);setError("");setNotice("");}}><Icon size={18} strokeWidth={1.8}/><span>{item.label}</span>{active===item.id&&<span className="nav-indicator"/>}</button>;})}</nav>
        <div className="sidebar-bottom"><div className="sidebar-tip"><Sparkles size={16}/><p>Good learning starts with material you trust.</p></div><span className="sidebar-foot">AI STUDY ASSISTANT</span></div>
      </aside>
      <main className="main-content">
        {error&&<div className="alert error-alert">{error}</div>}
        {notice&&<div className="alert success-alert">{notice}</div>}
        {active==="materials"&&<>
          <div className="page-heading"><div><div className="eyebrow">YOUR LIBRARY</div><h1>Study materials</h1><p className="page-description">Upload documents and make their content available to your study tools.</p></div><button className="primary-button" onClick={()=>picker.current?.click()}><Plus size={17}/> Add material</button></div>
          <section className="upload-panel" onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();addFiles(e.dataTransfer.files);}}>
            <div className="upload-illustration"><UploadCloud size={25} strokeWidth={1.6}/></div><h2>{busy?"Processing your material…":"Start with your study material"}</h2><p>Drop files here, or choose them from your device. Text is extracted for AI study tools.</p>
            <button className="outline-button" onClick={()=>picker.current?.click()} disabled={busy}> {busy?<LoaderCircle className="spin" size={15}/>:null} Choose files <ArrowUpRight size={15}/></button>
            <div className="file-types">PDF · DOCX · TXT · JPG · PNG · WEBP · TIFF</div>
            <input ref={picker} type="file" multiple accept=".pdf,.docx,.txt,.jpg,.jpeg,.jfif,.png,.webp,.bmp,.gif,.tif,.tiff" className="visually-hidden" onChange={e=>{addFiles(e.target.files);e.target.value="";}}/>
          </section>
          <div className="library-heading"><div><h2>Your files</h2><span>{files.length} {files.length===1?"file":"files"} uploaded and processed</span></div>{files.length>0&&<label className="search-box"><Search size={16}/><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Find a file"/></label>}</div>
          {visibleFiles.length?<div className="file-list">{visibleFiles.map((file,index)=>{const Icon=getFileIcon(file);return <div className="file-row" key={file.name+file.size+index}><span className="file-icon"><Icon size={19}/></span><div className="file-details"><strong>{file.name}</strong><span>{(file.size/1024/1024).toFixed(2)} MB · {file.meta?.characters?.toLocaleString()} extracted characters</span></div><span className="local-label">Processed</span><button className="icon-button" aria-label={"Remove "+file.name} onClick={()=>{setFiles(old=>old.filter(item=>item!==file));setMaterial(old=>files.filter(item=>item!==file).map(item=>item.text).join("\n\n"));}}><X size={17}/></button></div>;})}</div>:<div className="empty-state"><FolderOpen size={25}/><strong>{files.length?"No matching files":"Your library is ready"}</strong><span>{files.length?"Try another file name.":"Uploaded files will appear here."}</span></div>}
          {materialHint}
        </>}
        {active==="chat"&&<><div className="page-heading"><div><div className="eyebrow">ASK & UNDERSTAND</div><h1>AI chat</h1><p className="page-description">Ask questions and learn from your uploaded study material.</p></div>{levelControl}</div>{materialHint}<section className="tool-card chat-card"><div className="chat-messages">{messages.length?messages.map((m,i)=><div className={`chat-message ${m.role}`} key={i}><strong>{m.role==="user"?"You":"StudyDesk AI"}</strong><div>{m.content}</div></div>):<div className="empty-state"><MessageCircle size={26}/><strong>What would you like to understand?</strong><span>Ask a question about your material or any study topic.</span></div>}</div><form className="chat-form" onSubmit={sendChat}><input value={chatInput} onChange={e=>setChatInput(e.target.value)} placeholder="Ask a study question…" aria-label="Your question"/><button className="primary-button" disabled={busy||!chatInput.trim()}><Send size={16}/> Send</button></form></section></>}
        {active==="notes"&&<><div className="page-heading"><div><div className="eyebrow">ORGANIZE KNOWLEDGE</div><h1>Study notes</h1><p className="page-description">Generate clear, structured notes from your material or a topic.</p></div>{levelControl}</div><section className="tool-card"><label className="field-label">Topic (optional if material is uploaded)<input value={topic} onChange={e=>setTopic(e.target.value)} placeholder="e.g. Network security"/></label><label className="field-label">Note format<select value={noteStyle} onChange={e=>setNoteStyle(e.target.value)}><option>Headings and bullet points</option><option>Exam preparation notes</option><option>Short revision notes</option><option>Detailed notes with examples</option></select></label><button className="primary-button" onClick={generateNotes} disabled={busy||(!material.trim()&&!topic.trim())}>{busy?<LoaderCircle className="spin" size={16}/>:<Sparkles size={16}/>} Generate notes</button></section>{notes&&<article className="result-card"><div className="result-heading"><h2>Generated notes</h2><button className="outline-button" onClick={()=>navigator.clipboard.writeText(notes)}>Copy notes</button></div><div className="result-text">{notes}</div></article>}</>}
        {active==="summary"&&<><div className="page-heading"><div><div className="eyebrow">FOCUS ON THE ESSENTIALS</div><h1>Summarizer</h1><p className="page-description">Turn long study material into focused revision content.</p></div>{levelControl}</div>{materialHint}<section className="tool-card"><label className="field-label">Summary style<select value={summaryStyle} onChange={e=>setSummaryStyle(e.target.value)}><option>Short summary</option><option>Detailed summary</option><option>Key points</option><option>Exam-oriented summary</option></select></label><button className="primary-button" onClick={generateSummary} disabled={busy||!material.trim()}>{busy?<LoaderCircle className="spin" size={16}/>:<Sparkles size={16}/>} Generate summary</button></section>{summary&&<article className="result-card"><div className="result-heading"><h2>Study summary</h2><button className="outline-button" onClick={()=>navigator.clipboard.writeText(summary)}>Copy summary</button></div><div className="result-text">{summary}</div></article>}</>}
        {active==="quiz"&&<><div className="page-heading"><div><div className="eyebrow">TEST YOUR UNDERSTANDING</div><h1>Practice quiz</h1><p className="page-description">Generate multiple-choice questions and reveal answers as you attempt them.</p></div>{levelControl}</div><section className="tool-card quiz-settings"><label className="field-label">Quiz topic<input value={quizTopic} onChange={e=>setQuizTopic(e.target.value)} placeholder="Enter a topic or leave blank to use uploaded material"/></label><label className="field-label">Number of questions<select value={quizCount} onChange={e=>setQuizCount(Number(e.target.value))}><option value={30}>30 questions</option><option value={31}>31 questions</option><option value={32}>32 questions</option><option value={33}>33 questions</option><option value={34}>34 questions</option><option value={35}>35 questions</option></select></label>{materialHint}<button className="primary-button" onClick={generateQuiz} disabled={busy||(!material.trim()&&!quizTopic.trim())}>{busy?<LoaderCircle className="spin" size={16}/>:<Sparkles size={16}/>} Generate quiz</button></section>{quiz.length>0&&<section className="quiz-results"><div className="result-heading"><div><h2>{quizTopic||"Practice quiz"}</h2><span>{Object.keys(selected).length} of {quiz.length} attempted</span></div><div className="download-actions"><button className="outline-button" onClick={()=>downloadQuiz(false)} disabled={busy}><Download size={14}/> Questions PDF</button><button className="outline-button" onClick={()=>downloadQuiz(true)} disabled={busy}><Download size={14}/> PDF + answers</button></div></div>{quiz.map((q,i)=><article className="question-card" key={i}><h3>Q{i+1}. {q.question}</h3><div className="option-list">{q.options.map((o,j)=>{const letter=String.fromCharCode(65+j);const chosen=selected[i];const correct=q.answer===letter;return <button key={j} className={`quiz-option ${chosen?(correct?"option-correct":chosen===letter?"option-wrong":""):""}`} disabled={!!chosen} onClick={()=>setSelected(old=>({...old,[i]:letter}))}><span>{letter}</span>{o.label.replace(/^[A-D][\).]\s*/,"")}</button>;})}</div>{selected[i]&&<div className={`answer-feedback ${selected[i]===q.answer?"feedback-correct":"feedback-wrong"}`}><strong>{selected[i]===q.answer?"Correct answer":"Correct answer: "+q.answer}</strong><p>{q.explanation}</p></div>}</article>)}</section>}</>}
      </main>
    </div>
  </div>;
}
