import { useRef, useState } from "react";
import { BookOpen, MessageCircle, NotebookPen, ListChecks, FileText, UploadCloud, Search, Plus, X, File, FileImage, FileType2, Menu, ArrowUpRight, Sparkles, FolderOpen } from "lucide-react";

const sections = [
  { id:"materials", label:"Study materials", icon:BookOpen },
  { id:"chat", label:"AI chat", icon:MessageCircle },
  { id:"notes", label:"Notes", icon:NotebookPen },
  { id:"summary", label:"Summarizer", icon:FileText },
  { id:"quiz", label:"Quiz", icon:ListChecks }
];

function getFileIcon(file) {
  if (file.type.startsWith("image/")) return FileImage;
  if (file.name.toLowerCase().endsWith(".pdf")) return FileType2;
  return File;
}

export default function App() {
  const [active,setActive] = useState("materials");
  const [files,setFiles] = useState([]);
  const [query,setQuery] = useState("");
  const [mobileMenu,setMobileMenu] = useState(false);
  const picker = useRef(null);
  const current = sections.find(item => item.id === active);
  const visibleFiles = files.filter(file => file.name.toLowerCase().includes(query.toLowerCase()));

  function addFiles(selected) {
    const incoming = Array.from(selected || []);
    setFiles(old => {
      const known = new Set(old.map(file => file.name + file.size));
      return [...old,...incoming.filter(file => !known.has(file.name + file.size))];
    });
  }

  return <div className="app-shell">
    <header className="topbar">
      <a className="brand" href="#" onClick={e=>e.preventDefault()}><span className="brand-mark"><BookOpen size={19}/></span><span>study<span className="brand-light">desk</span></span></a>
      <div className="topbar-note"><span className="status-dot"/> Your personal study workspace</div>
      <button className="mobile-menu-button" aria-label="Toggle navigation" onClick={()=>setMobileMenu(!mobileMenu)}><Menu size={21}/></button>
    </header>
    <div className="workspace">
      <aside className={`sidebar ${mobileMenu ? "sidebar-open" : ""}`}>
        <div className="nav-caption">WORKSPACE</div>
        <nav aria-label="Main navigation">{sections.map(item=>{
          const Icon=item.icon;
          return <button key={item.id} className={`nav-item ${active===item.id?"active":""}`} onClick={()=>{setActive(item.id);setMobileMenu(false);}}>
            <Icon size={18} strokeWidth={1.8}/><span>{item.label}</span>{active===item.id&&<span className="nav-indicator"/>}
          </button>;
        })}</nav>
        <div className="sidebar-bottom"><div className="sidebar-tip"><Sparkles size={16}/><p>Good learning starts with material you trust.</p></div><span className="sidebar-foot">AI STUDY ASSISTANT</span></div>
      </aside>
      <main className="main-content">
        {active==="materials" ? <>
          <div className="page-heading"><div><div className="eyebrow">YOUR LIBRARY</div><h1>Study materials</h1><p className="page-description">Bring your learning material together in one place.</p></div><button className="primary-button" onClick={()=>picker.current?.click()}><Plus size={17}/> Add material</button></div>
          <section className="upload-panel" onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();addFiles(e.dataTransfer.files);}}>
            <div className="upload-illustration"><UploadCloud size={25} strokeWidth={1.6}/></div><h2>Start with your study material</h2><p>Drop your files here, or choose them from your device.</p>
            <button className="outline-button" onClick={()=>picker.current?.click()}>Choose files <ArrowUpRight size={15}/></button>
            <div className="file-types">PDF · DOCX · TXT · JPG · PNG · WEBP · TIFF</div>
            <input ref={picker} type="file" multiple accept=".pdf,.docx,.txt,.jpg,.jpeg,.jfif,.png,.webp,.bmp,.gif,.tif,.tiff" className="visually-hidden" onChange={e=>addFiles(e.target.files)}/>
          </section>
          <div className="library-heading"><div><h2>Your files</h2><span>{files.length} {files.length===1?"file":"files"} selected on this device</span></div>{files.length>0&&<label className="search-box"><Search size={16}/><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Find a file"/></label>}</div>
          {visibleFiles.length ? <div className="file-list">{visibleFiles.map((file,index)=>{const Icon=getFileIcon(file);return <div className="file-row" key={file.name+file.size+index}><span className="file-icon"><Icon size={19}/></span><div className="file-details"><strong>{file.name}</strong><span>{(file.size/1024/1024).toFixed(2)} MB</span></div><span className="local-label">Selected</span><button className="icon-button" aria-label={`Remove ${file.name}`} onClick={()=>setFiles(old=>old.filter(item=>item!==file))}><X size={17}/></button></div>;})}</div>
          : <div className="empty-state"><FolderOpen size={25}/><strong>{files.length?"No matching files":"Your library is ready"}</strong><span>{files.length?"Try another file name.":"Files you choose will appear here."}</span></div>}
          <p className="privacy-note"><span/> Files are currently selected in this browser only. Server upload and document processing will be connected in the backend integration step.</p>
        </> : <section className="coming-screen"><div className="eyebrow">STUDY WORKSPACE</div><div className="coming-icon">{current&&<current.icon size={25}/>}</div><h1>{current?.label}</h1><p>This workspace is part of the redesign. Its existing Gemini and document-processing features will be connected after the API layer is separated from the current Streamlit app.</p><button className="outline-button" onClick={()=>setActive("materials")}>Back to study materials</button></section>}
      </main>
    </div>
  </div>;
}