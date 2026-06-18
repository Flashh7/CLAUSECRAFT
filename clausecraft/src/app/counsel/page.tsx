"use client";

import { useState, useRef, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Badge } from "@/components/ui/badge";
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";
import { 
  Send, 
  Paperclip, 
  FileText, 
  Scale, 
  PanelRightClose, 
  PanelRightOpen,
  PanelLeftClose,
  PanelLeftOpen,
  UploadCloud,
  ShieldAlert,
  Clock,
  Menu,
  Loader2,
  Plus,
  MessageSquare
} from "lucide-react";
import ReactMarkdown from 'react-markdown';

// Future-Proof Matter Schema
type Message = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
};

type Clause = {
  source: string;
  clause_number: string;
  title?: string;
};

type TimelineEvent = {
  date: string;
  event: string;
};

type Document = {
  name: string;
};

type Matter = {
  id: string;
  title: string;
  createdAt: string;
  messages: Message[];
  metadata: {
    matterType: string;
    riskLevel: string;
    confidence: number;
    clauses: Clause[];
    timeline: TimelineEvent[];
    documents: Document[];
  };
};

// Dynamic History
type MatterSummary = {
  id: string;
  title: string;
  date: string;
};

export default function CounselPage() {
  const [intelligenceOpen, setIntelligenceOpen] = useState(true);
  const [historyOpen, setHistoryOpen] = useState(true);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [streamingStatus, setStreamingStatus] = useState("");
  const scrollAreaRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  
  const toggleIntelligence = () => setIntelligenceOpen(!intelligenceOpen);
  const toggleHistory = () => setHistoryOpen(!historyOpen);

  const [historyList, setHistoryList] = useState<MatterSummary[]>([]);

  // Fetch History on Mount
  useEffect(() => {
    const fetchHistory = async () => {
      try {
        const res = await fetch("http://localhost:8000/api/matters");
        const data = await res.json();
        setHistoryList(data);
      } catch (err) {
        console.error("Failed to load history", err);
      }
    };
    fetchHistory();
  }, []);

  const getEmptyMatter = (): Matter => ({
    id: "",
    title: "New Dispute",
    createdAt: new Date().toISOString(),
    messages: [
      {
        id: "msg-1",
        role: "assistant",
        content: "Welcome to ClauseCraft Counsel. I am your specialized AI construction law assistant. Please describe your dispute or upload a bespoke contract to begin analysis."
      }
    ],
    metadata: {
      matterType: "Pending",
      riskLevel: "Unknown",
      confidence: 0,
      clauses: [],
      timeline: [],
      documents: []
    }
  });

  const [activeMatter, setActiveMatter] = useState<Matter>(getEmptyMatter());

  const createNewMatter = () => {
    setActiveMatter(getEmptyMatter());
  };

  const loadMatter = async (id: string) => {
    try {
      const res = await fetch(`http://localhost:8000/api/matters/${id}`);
      const data = await res.json();
      setActiveMatter({
        id: data.id,
        title: data.title,
        createdAt: new Date().toISOString(),
        messages: data.messages,
        metadata: data.metadata
      });
    } catch (err) {
      console.error("Failed to load matter", err);
    }
  };

  // Auto-scroll to bottom
  useEffect(() => {
    if (scrollAreaRef.current) {
      scrollAreaRef.current.scrollTop = scrollAreaRef.current.scrollHeight;
    }
  }, [activeMatter.messages, streamingStatus]);

  const triggerFileUpload = () => {
    if (fileInputRef.current) {
      fileInputRef.current.click();
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsUploading(true);
    const formData = new FormData();
    formData.append("file", file);
    
    // We append the matter_id as a query param since the FastAPI endpoint expects it as a function argument
    // e.g., /api/upload?matter_id=m-1234
    
    try {
      const response = await fetch(`http://localhost:8000/api/upload?matter_id=${activeMatter.id}`, {
        method: "POST",
        body: formData,
      });

      if (response.ok) {
        // Update the Matter state to reflect the uploaded document
        setActiveMatter(prev => ({
          ...prev,
          metadata: {
            ...prev.metadata,
            documents: [...prev.metadata.documents, { name: file.name }]
          }
        }));
      } else {
        console.error("Upload failed");
      }
    } catch (error) {
      console.error("Upload error:", error);
    } finally {
      setIsUploading(false);
      // Reset file input so the same file can be uploaded again if needed
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  const handleSend = async () => {
    if (!input.trim() || isStreaming) return;
    
    const userMessage: Message = { id: Date.now().toString(), role: "user", content: input };
    const newMessages = [...activeMatter.messages, userMessage];
    
    setActiveMatter(prev => ({
      ...prev,
      messages: newMessages
    }));
    setInput("");
    setIsStreaming(true);
    setStreamingStatus("Initializing...");

    // Create a temporary assistant message ID for streaming
    const assistantMessageId = (Date.now() + 1).toString();
    setActiveMatter(prev => ({
      ...prev,
      messages: [...prev.messages, { id: assistantMessageId, role: "assistant", content: "" }]
    }));

    try {
      const response = await fetch("http://localhost:8000/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          matter_id: activeMatter.id,
          messages: newMessages.map(m => ({ role: m.role, content: m.content })),
          conversation_history: [],
          uploaded_documents: activeMatter.metadata.documents
        })
      });

      if (!response.body) throw new Error("No response body");

      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let currentContent = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split("\n");
        
        let currentEvent = "";
        
        for (const line of lines) {
          if (line.startsWith("event: ")) {
            currentEvent = line.replace("event: ", "").trim();
          } else if (line.startsWith("data: ")) {
            const dataStr = line.replace("data: ", "").trim();
            if (!dataStr) continue;
            
            const data = JSON.parse(dataStr);
            
            if (currentEvent === "status") {
              setStreamingStatus(data.stage);
            } 
            else if (currentEvent === "metadata") {
              setActiveMatter(prev => {
                // If this is the first message generating the DB matter, update our ID
                const newId = data.matter_id || prev.id;
                if (data.matter_id && data.matter_id !== prev.id) {
                  // Refresh history sidebar asynchronously
                  fetch("http://localhost:8000/api/matters")
                    .then(r => r.json())
                    .then(d => setHistoryList(d));
                }
                
                return {
                  ...prev,
                  id: newId,
                  metadata: {
                    ...prev.metadata,
                    matterType: data.matterType || prev.metadata.matterType,
                    riskLevel: data.riskLevel || prev.metadata.riskLevel,
                    confidence: data.confidence || prev.metadata.confidence,
                    timeline: data.timeline || prev.metadata.timeline,
                    documents: data.documents || prev.metadata.documents
                  }
                };
              });
            }
            else if (currentEvent === "citation") {
              setActiveMatter(prev => ({
                ...prev,
                metadata: {
                  ...prev.metadata,
                  clauses: [...prev.metadata.clauses, data]
                }
              }));
            }
            else if (currentEvent === "content") {
              currentContent += data.text;
              setActiveMatter(prev => ({
                ...prev,
                messages: prev.messages.map(msg => 
                  msg.id === assistantMessageId 
                    ? { ...msg, content: currentContent }
                    : msg
                )
              }));
            }
            else if (currentEvent === "done") {
              setIsStreaming(false);
              setStreamingStatus("");
            }
          }
        }
      }
    } catch (error) {
      console.error("Chat error:", error);
      setIsStreaming(false);
      setStreamingStatus("");
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="flex h-screen bg-background overflow-hidden text-foreground">
      
      {/* LEFT PANEL: Matter History Sidebar */}
      {historyOpen && (
        <aside className="hidden lg:flex w-64 border-r border-border/50 bg-card/10 flex-col h-full shrink-0 animate-in slide-in-from-left-2 duration-300">
          <div className="h-14 flex items-center justify-between px-4 border-b border-border/50 shrink-0">
            <span className="font-semibold text-sm">Recent Matters</span>
            <Button variant="ghost" size="icon" onClick={createNewMatter} className="h-8 w-8 text-muted-foreground hover:text-foreground">
              <Plus className="w-4 h-4" />
            </Button>
          </div>
          <ScrollArea className="flex-1 p-3">
            <div className="space-y-1">
              {historyList.map((item) => (
                <button 
                  key={item.id} 
                  onClick={() => loadMatter(item.id)}
                  className={`w-full flex items-center gap-3 text-left px-3 py-2.5 rounded-md text-sm transition-colors group ${activeMatter.id === item.id ? 'bg-primary/10 text-primary' : 'hover:bg-muted/50 text-muted-foreground hover:text-foreground'}`}
                >
                  <MessageSquare className={`w-4 h-4 shrink-0 ${activeMatter.id === item.id ? 'text-primary' : 'text-muted-foreground group-hover:text-primary'}`} />
                  <span className="truncate flex-1">{item.title}</span>
                </button>
              ))}
            </div>
          </ScrollArea>
        </aside>
      )}

      {/* CENTER PANEL: Chat Interface */}
      <div className="flex flex-col h-full flex-1 transition-all duration-300 min-w-0">
        
        {/* Header */}
        <header className="h-14 flex items-center justify-between px-4 border-b border-border/50 shrink-0 bg-background/95 backdrop-blur">
          <div className="flex items-center gap-3">
            {/* Left Sidebar Toggle */}
            <Button 
              variant="ghost" 
              size="icon" 
              onClick={toggleHistory}
              className="hidden lg:flex h-8 w-8 text-muted-foreground hover:text-foreground"
            >
              {historyOpen ? <PanelLeftClose className="w-4 h-4" /> : <PanelLeftOpen className="w-4 h-4" />}
            </Button>
            
            <Separator orientation="vertical" className="h-4 hidden lg:block" />

            <div className="flex items-center gap-2">
              <Scale className="w-5 h-5 text-primary" />
              <span className="font-semibold tracking-tight text-lg">ClauseCraft Counsel</span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* Mobile Sidebar Trigger */}
            <Sheet>
              <SheetTrigger render={<Button variant="ghost" size="icon" className="lg:hidden text-muted-foreground hover:text-foreground" />}>
                <Menu className="w-5 h-5" />
              </SheetTrigger>
              <SheetContent side="right" className="w-[300px] sm:w-[400px] p-0 border-l border-border/50 bg-card/30 backdrop-blur-xl">
                <IntelligenceSidebar matter={activeMatter} />
              </SheetContent>
            </Sheet>
            
            {/* Desktop Intelligence Toggle */}
            <Button 
              variant="ghost" 
              size="icon" 
              onClick={toggleIntelligence}
              className="hidden lg:flex text-muted-foreground hover:text-foreground"
            >
              {intelligenceOpen ? <PanelRightClose className="w-5 h-5" /> : <PanelRightOpen className="w-5 h-5" />}
            </Button>
          </div>
        </header>

        {/* Chat Feed */}
        <div className="flex-1 p-4 md:p-8 overflow-y-auto" ref={scrollAreaRef}>
          <div className="max-w-3xl mx-auto space-y-8 pb-10">
            
            {activeMatter.messages.map((msg) => (
              <div key={msg.id} className={`flex gap-4 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}>
                <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${msg.role === 'user' ? 'bg-muted' : 'bg-primary/20'}`}>
                  {msg.role === 'user' ? <span className="text-xs font-medium">You</span> : <Scale className="w-4 h-4 text-primary" />}
                </div>
                
                <div className={`flex-1 mt-1 ${msg.role === 'user' ? 'bg-muted/30 px-4 py-3 rounded-2xl rounded-tr-none text-sm border border-border/50 max-w-[80%]' : 'space-y-4 overflow-hidden'}`}>
                  {msg.role === 'assistant' && msg.id === activeMatter.messages[activeMatter.messages.length - 1].id && isStreaming && streamingStatus && msg.content === "" ? (
                    <div className="flex items-center gap-2 text-sm text-primary animate-pulse py-2">
                      <Loader2 className="w-4 h-4 animate-spin" />
                      {streamingStatus}
                    </div>
                  ) : msg.role === 'user' ? (
                    <div className="whitespace-pre-wrap">{msg.content}</div>
                  ) : (
                    <div className="prose prose-invert prose-sm max-w-none prose-headings:text-primary prose-a:text-blue-400">
                      <ReactMarkdown>{msg.content}</ReactMarkdown>
                    </div>
                  )}
                </div>
              </div>
            ))}

          </div>
        </div>

        {/* Input Area */}
        <div className="p-4 md:p-6 bg-background/80 backdrop-blur-md border-t border-border/50 shrink-0">
          <div className="max-w-3xl mx-auto flex flex-col gap-3">
            
            {/* Hidden File Input */}
            <input 
              type="file" 
              ref={fileInputRef} 
              className="hidden" 
              onChange={handleFileUpload} 
              accept=".pdf,.docx,.txt"
            />
            
            <div className="flex gap-2">
              <Button 
                variant="outline" 
                size="sm" 
                className="text-xs h-8 border-border/50 bg-card/50 hover:bg-muted"
                onClick={triggerFileUpload}
                disabled={isUploading || isStreaming}
              >
                {isUploading ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin text-primary" /> : <UploadCloud className="w-3.5 h-3.5 mr-1.5 text-primary" />} 
                {isUploading ? "Uploading..." : "Attach Contract"}
              </Button>
              <Button 
                variant="outline" 
                size="sm" 
                className="text-xs h-8 border-border/50 bg-card/50 hover:bg-muted"
                onClick={triggerFileUpload}
                disabled={isUploading || isStreaming}
              >
                {isUploading ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin text-primary" /> : <Paperclip className="w-3.5 h-3.5 mr-1.5 text-primary" />} 
                {isUploading ? "Uploading..." : "Attach Evidence"}
              </Button>
            </div>
            <div className={`relative flex items-end gap-2 bg-muted/20 border border-border/50 rounded-2xl p-2 transition-all ${isStreaming ? 'opacity-50 pointer-events-none' : 'focus-within:ring-1 focus-within:ring-primary focus-within:border-primary'}`}>
              <textarea 
                className="w-full bg-transparent border-none focus:ring-0 resize-none min-h-[44px] max-h-32 text-sm p-2 outline-none disabled:opacity-50"
                placeholder="Ask a question or provide more details..."
                rows={1}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={isStreaming}
              />
              <Button size="icon" onClick={handleSend} disabled={!input.trim() || isStreaming} className="h-10 w-10 shrink-0 rounded-xl bg-primary text-primary-foreground hover:bg-primary/90 self-end mb-0.5">
                <Send className="w-4 h-4" />
              </Button>
            </div>
            <div className="text-[10px] text-center text-muted-foreground mt-2">
              ClauseCraft Counsel uses AI. Check important legal references against original source documents.
            </div>
          </div>
        </div>

      </div>

      {/* RIGHT PANEL: Desktop Intelligence Sidebar */}
      {intelligenceOpen && (
        <aside className="hidden lg:flex w-1/3 xl:w-1/4 border-l border-border/50 bg-card/20 backdrop-blur-xl flex-col h-full shrink-0 animate-in slide-in-from-right-2 duration-300">
          <IntelligenceSidebar matter={activeMatter} />
        </aside>
      )}

    </div>
  );
}

// Extracted Sidebar Component for reuse in Desktop and Mobile views
function IntelligenceSidebar({ matter }: { matter: Matter }) {
  const { metadata } = matter;

  return (
    <div className="flex flex-col h-full overflow-hidden text-foreground">
      <div className="h-14 flex items-center px-4 border-b border-border/50 shrink-0 bg-muted/10">
        <h2 className="text-sm font-semibold uppercase tracking-wider flex items-center gap-2">
          <ShieldAlert className="w-4 h-4 text-primary" /> Matter Intelligence
        </h2>
      </div>

      <ScrollArea className="flex-1 p-4">
        <div className="space-y-6">
          
          {/* Active Matter Section */}
          <div className="space-y-2">
            <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Active Matter</h3>
            <div className="bg-background/50 border border-border/50 rounded-md p-3">
              <div className="text-sm font-medium">{metadata.matterType || "Pending"}</div>
              <div className="text-xs text-muted-foreground mt-0.5">{matter.title}</div>
            </div>
          </div>

          {/* Risk Meter Section */}
          <div className="space-y-2">
            <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Risk Assessment</h3>
            <div className="bg-background/50 border border-border/50 rounded-md p-4 flex flex-col items-center justify-center text-center">
              {metadata.riskLevel === "Unknown" ? (
                <div className="text-sm text-muted-foreground">Awaiting sufficient evidence</div>
              ) : (
                <>
                  <div className={`text-3xl font-bold mb-1 ${metadata.riskLevel === 'High' ? 'text-destructive' : metadata.riskLevel === 'Medium' ? 'text-yellow-500' : 'text-green-500'}`}>
                    {metadata.confidence}%
                  </div>
                  <Badge variant="outline" className={`text-[10px] ${metadata.riskLevel === 'High' ? 'border-destructive/30 text-destructive bg-destructive/10' : metadata.riskLevel === 'Medium' ? 'border-yellow-500/30 text-yellow-500 bg-yellow-500/10' : 'border-green-500/30 text-green-500 bg-green-500/10'}`}>
                    {metadata.riskLevel} Risk
                  </Badge>
                </>
              )}
            </div>
          </div>

          {/* Relevant Clauses Section */}
          <div className="space-y-2">
            <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Matched Clauses</h3>
            {metadata.clauses.length === 0 ? (
              <div className="text-xs text-muted-foreground italic">No clauses retrieved yet.</div>
            ) : (
              <div className="space-y-2">
                {metadata.clauses.map((clause, idx) => (
                  <div key={idx} className="bg-primary/5 border border-primary/20 rounded-md p-2 hover:bg-primary/10 transition-colors cursor-pointer animate-in fade-in zoom-in duration-300">
                    <div className="text-xs font-medium text-foreground">{clause.source} Clause {clause.clause_number}</div>
                    {clause.title && <div className="text-[10px] text-muted-foreground mt-0.5 truncate">{clause.title}</div>}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Timeline Section */}
          <div className="space-y-2">
            <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
              <Clock className="w-3.5 h-3.5" /> Timeline Recon
            </h3>
            {metadata.timeline.length === 0 ? (
              <div className="text-xs text-muted-foreground italic">Insufficient dates extracted.</div>
            ) : (
              <div className="bg-background/50 border border-border/50 rounded-md p-3 relative before:absolute before:left-3.5 before:top-4 before:bottom-4 before:w-px before:bg-border">
                <div className="space-y-3 pl-5 relative">
                  {metadata.timeline.map((event, idx) => (
                    <div key={idx} className="relative animate-in slide-in-from-bottom-2 duration-300">
                      <div className="absolute -left-[23px] top-1 w-2 h-2 rounded-full bg-primary" />
                      <div className="text-[10px] font-bold text-primary">{event.date}</div>
                      <div className="text-xs text-foreground">{event.event}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Evidence Section */}
          <div className="space-y-2">
            <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Evidence Locker</h3>
            <div className="space-y-1.5">
              {metadata.documents.length === 0 ? (
                 <div className="text-xs text-muted-foreground italic">No documents attached.</div>
              ) : (
                metadata.documents.map((doc, idx) => (
                  <div key={idx} className="flex items-center gap-2 p-2 rounded-md hover:bg-muted/20 cursor-pointer animate-in fade-in">
                    <FileText className="w-3.5 h-3.5 text-primary shrink-0" />
                    <span className="text-xs text-foreground truncate">{doc.name}</span>
                  </div>
                ))
              )}
            </div>
          </div>

        </div>
      </ScrollArea>
    </div>
  );
}
