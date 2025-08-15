// src/components/layout.tsx
import { Button } from "@/components/ui/button"
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet"
import { Menu } from "lucide-react"
import { ThemeToggle } from "@/components/ThemeToggle"
import { Link, NavLink } from "react-router-dom"

export function Layout({ children }: { children: React.ReactNode }) {
    return (
        <div className="min-h-screen w-full flex flex-col">
            {/* Mobile header (unchanged behavior) */}
            <header className="flex h-14 items-center gap-4 border-b bg-muted/40 px-4 lg:h-[60px] lg:px-6 md:hidden">
                <Sheet>
                    <SheetTrigger asChild>
                        <Button
                            variant="outline"
                            size="icon"
                            className="shrink-0"
                            aria-label="Open navigation menu"
                        >
                            <Menu className="h-5 w-5" />
                        </Button>
                    </SheetTrigger>
                    <SheetContent side="left" className="flex flex-col">
                        <nav className="grid gap-2 text-lg font-medium">
                            <Link to="/" className="flex items-center gap-2 text-lg font-semibold">
                                <span>Soccer Analyzer</span>
                            </Link>
                            <Link
                                to="/"
                                className="mx-[-0.65rem] flex items-center gap-4 rounded-xl px-3 py-2 text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
                            >
                                Match Analysis
                            </Link>
                            <Link
                                to="/history"
                                className="mx-[-0.65rem] flex items-center gap-4 rounded-xl px-3 py-2 text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
                            >
                                History
                            </Link>
                        </nav>
                    </SheetContent>
                </Sheet>
                <div className="w-full flex-1">
                    <h1 className="text-lg font-semibold">Soccer Commentary Analyzer</h1>
                </div>
                <ThemeToggle />
            </header>

            {/* Desktop top menu (non-sticky) */}
            <header className="hidden md:flex items-center gap-6 border-b bg-muted/40 px-6 h-[60px]">
                <Link to="/" className="font-semibold whitespace-nowrap">Soccer Analyzer</Link>
                <nav className="flex items-center gap-1 text-sm">
                    <NavLink
                        to="/"
                        className={({ isActive }) =>
                            `rounded-md px-3 py-2 text-muted-foreground hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50 ${isActive ? "bg-accent/40 text-foreground" : ""}`
                        }
                    >
                        Match Analysis
                    </NavLink>
                    <NavLink
                        to="/history"
                        className={({ isActive }) =>
                            `rounded-md px-3 py-2 text-muted-foreground hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50 ${isActive ? "bg-accent/40 text-foreground" : ""}`
                        }
                    >
                        History
                    </NavLink>
                </nav>
                <div className="ml-auto">
                    <ThemeToggle />
                </div>
            </header>

            <main className="flex-1 flex flex-col gap-6 px-4 sm:px-6 lg:px-8 py-6 max-w-screen-lg w-full mx-auto">
                {children}
            </main>
        </div>
    )
}