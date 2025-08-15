import React from "react";
import { toast } from "sonner";

interface ErrorBoundaryState {
  hasError: boolean;
}

export class ErrorBoundary extends React.Component<React.PropsWithChildren, ErrorBoundaryState> {
  state: ErrorBoundaryState = { hasError: false };

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { hasError: true };
  }

  componentDidCatch(error: unknown) {
    // Show user-friendly message
    const message = error instanceof Error ? error.message : "Something went wrong";
    toast.error("Unexpected error", { description: message });
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="w-full p-6 text-center text-sm text-muted-foreground">
          Something went wrong. Please try again.
        </div>
      );
    }
    return this.props.children;
  }
}
