// src/components/file-uploader.tsx
import { useDropzone, type DropzoneOptions } from "react-dropzone";
import { UploadCloud, X, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

interface FileUploaderProps extends DropzoneOptions {
    value?: File[];
    onChange?: (files: File[]) => void;
    onRemove?: (file: File) => void;
    isLoading?: boolean;
}

export function FileUploader({
    value = [],
    onChange,
    onRemove,
    isLoading = false,
    ...dropzoneOptions
}: FileUploaderProps) {
    const { getRootProps, getInputProps, isDragActive } = useDropzone({
        accept: {
            "text/*": [".txt", ".pdf", ".doc", ".docx"],
            "audio/*": [".mp3", ".wav"],
            "video/*": [".mp4"],
        },
        maxFiles: 1,
        onDrop: (acceptedFiles: File[]) => {
            onChange?.(acceptedFiles);
        },
        ...dropzoneOptions,
    });

    return (
        <div className="space-y-4">
            <div
                {...getRootProps()}
                className={cn(
                    "border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors",
                    isDragActive ? "border-primary bg-primary/10" : "border-muted-foreground/30"
                )}
            >
                <input {...getInputProps()} />
                <div className="flex flex-col items-center justify-center gap-2">
                    <UploadCloud className="h-8 w-8 text-muted-foreground" />
                    <div className="text-sm text-muted-foreground">
                        {isDragActive ? (
                            <p>Drop the file here...</p>
                        ) : (
                            <p>
                                Drag & drop a file here, or click to select
                            </p>
                        )}
                    </div>
                    <p className="text-xs text-muted-foreground/70">
                        Supported formats: TXT, PDF, DOC, DOCX, MP3, WAV, MP4
                    </p>
                </div>
            </div>

            {value.length > 0 && (
                <div className="space-y-2">
                    {value.map((file, index) => (
                        <div
                            key={index}
                            className="flex items-center justify-between gap-2 rounded-md border p-3"
                        >
                            <div className="flex items-center gap-2">
                                {isLoading ? (
                                    <Loader2 className="h-4 w-4 animate-spin" />
                                ) : (
                                    <div className="flex-1 truncate">
                                        <p className="truncate text-sm font-medium">{file.name}</p>
                                        <p className="text-xs text-muted-foreground">
                                            {(file.size / 1024 / 1024).toFixed(2)} MB
                                        </p>
                                    </div>
                                )}
                            </div>
                            <Button
                                type="button"
                                variant="ghost"
                                size="icon"
                                className="h-8 w-8"
                                onClick={(e) => {
                                    e.stopPropagation();
                                    onRemove?.(file);
                                }}
                                disabled={isLoading}
                            >
                                <X className="h-4 w-4" />
                            </Button>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}