// src/components/ui/file-input.tsx
import * as React from "react"
import { cn } from "@/lib/utils"

interface FileInputProps extends React.InputHTMLAttributes<HTMLInputElement> {
    label?: string
    description?: string
}

const FileInput = React.forwardRef<HTMLInputElement, FileInputProps>(
    ({ className, label, description, ...props }, ref) => {
        return (
            <div className="grid w-full max-w-sm items-center gap-1.5">
                {label && <label className="text-sm font-medium">{label}</label>}
                <input
                    type="file"
                    className={cn(
                        "border-input bg-background placeholder:text-muted-foreground focus-visible:ring-ring flex h-10 w-full rounded-md border px-3 py-2 text-sm file:mr-4 file:rounded-md file:border-0 file:bg-primary file:px-4 file:py-1 file:text-sm file:font-medium file:text-primary-foreground file:hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 disabled:cursor-not-allowed disabled:opacity-50",
                        className
                    )}
                    ref={ref}
                    {...props}
                />
                {description && (
                    <p className="text-sm text-muted-foreground">{description}</p>
                )}
            </div>
        )
    }
)
FileInput.displayName = "FileInput"

export { FileInput }