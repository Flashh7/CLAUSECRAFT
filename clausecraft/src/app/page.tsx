import Link from "next/link";
import { Button } from "@/components/ui/button";
import { ArrowRight, Scale, ShieldCheck, FileSearch } from "lucide-react";

export default function LandingPage() {
  return (
    <div className="flex flex-col min-h-screen bg-background relative overflow-hidden">
      {/* Background Glows */}
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-full max-w-4xl h-[500px] bg-primary/20 blur-[120px] rounded-full pointer-events-none" />

      {/* Navigation */}
      <header className="flex items-center justify-between px-8 py-6 z-10">
        <div className="flex items-center gap-2 text-2xl font-semibold tracking-tight text-foreground">
          <Scale className="w-8 h-8 text-primary" />
          ClauseCraft
        </div>
        <nav className="hidden md:flex items-center gap-8 text-sm font-medium text-muted-foreground">
          <Link href="#features" className="hover:text-primary transition-colors">Features</Link>
          <Link href="#frameworks" className="hover:text-primary transition-colors">Supported Contracts</Link>
          <Link href="#testimonials" className="hover:text-primary transition-colors">Testimonials</Link>
        </nav>
        <div className="flex items-center gap-4">
          <Button variant="ghost" className="hidden sm:flex text-muted-foreground hover:text-foreground">Sign In</Button>
          <Link href="/counsel">
            <Button className="bg-primary text-primary-foreground hover:bg-primary/90">
              Start Analysis <ArrowRight className="w-4 h-4 ml-2" />
            </Button>
          </Link>
        </div>
      </header>

      {/* Hero Section */}
      <main className="flex-1 flex flex-col items-center justify-center text-center px-4 pt-24 pb-32 z-10">
        <div className="inline-flex items-center gap-2 px-3 py-1 mb-8 rounded-full border border-primary/30 bg-primary/10 text-primary text-sm font-medium">
          <span className="flex h-2 w-2 rounded-full bg-primary animate-pulse" />
          Construction Contract Intelligence
        </div>
        
        <h1 className="text-5xl md:text-7xl font-extrabold tracking-tight text-foreground max-w-4xl mb-6">
          Construction Disputes.<br />
          <span className="text-transparent bg-clip-text bg-gradient-to-r from-primary to-blue-400">
            Resolved Through AI Counsel.
          </span>
        </h1>
        
        <p className="text-xl text-muted-foreground max-w-2xl mb-10 leading-relaxed">
          AI-powered clause analysis for contractors, lawyers, and claims consultants. Chat with ClauseCraft Counsel to get actionable legal memorandums and risk assessments in seconds.
        </p>
        
        <div className="flex flex-col sm:flex-row items-center gap-4">
          <Link href="/counsel">
            <Button size="lg" className="h-14 px-8 text-lg bg-primary text-primary-foreground hover:bg-primary/90 shadow-[0_0_20px_rgba(0,240,255,0.3)]">
              Open ClauseCraft Counsel <ArrowRight className="w-5 h-5 ml-2" />
            </Button>
          </Link>
        </div>

        {/* Feature Highlights */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8 mt-24 w-full max-w-5xl text-left">
          <div className="p-6 rounded-2xl border border-white/5 bg-card/30 backdrop-blur-md hover:bg-card/50 transition-colors">
            <div className="w-12 h-12 rounded-lg bg-primary/10 flex items-center justify-center mb-4">
              <FileSearch className="w-6 h-6 text-primary" />
            </div>
            <h3 className="text-xl font-semibold text-foreground mb-2">Instant Clause Retrieval</h3>
            <p className="text-muted-foreground leading-relaxed">Automatically find relevant clauses from CPWD GCC, Railways GCC, and your custom uploaded contracts with high accuracy.</p>
          </div>
          <div className="p-6 rounded-2xl border border-white/5 bg-card/30 backdrop-blur-md hover:bg-card/50 transition-colors">
            <div className="w-12 h-12 rounded-lg bg-primary/10 flex items-center justify-center mb-4">
              <ShieldCheck className="w-6 h-6 text-primary" />
            </div>
            <h3 className="text-xl font-semibold text-foreground mb-2">Risk Assessment Engine</h3>
            <p className="text-muted-foreground leading-relaxed">Get objective probability scores for Contractor vs. Employer positions and identify potential hallucination risks.</p>
          </div>
          <div className="p-6 rounded-2xl border border-white/5 bg-card/30 backdrop-blur-md hover:bg-card/50 transition-colors">
            <div className="w-12 h-12 rounded-lg bg-primary/10 flex items-center justify-center mb-4">
              <Scale className="w-6 h-6 text-primary" />
            </div>
            <h3 className="text-xl font-semibold text-foreground mb-2">Drafting & Strategy</h3>
            <p className="text-muted-foreground leading-relaxed">Generate dynamic case assessments, Claim Notices, and Arbitration Submissions grounded in contract specifics.</p>
          </div>
        </div>
      </main>
    </div>
  );
}
