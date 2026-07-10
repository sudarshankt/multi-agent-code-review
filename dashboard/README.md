# Cap PR Review Dashboard

React 18 + TypeScript + Vite + TailwindCSS dashboard for the AI multi-agent PR review system.

## Quick Start

```bash
# Install dependencies
npm install

# Start dev server (proxies /api to http://localhost:8000)
npm run dev

# Open http://localhost:5173
```

## Features

- ✅ **Manual PR Analysis**: Input GitHub PR URL, submit for analysis
- ✅ **Live Progress**: Real-time status updates via Server-Sent Events (SSE)
- ✅ **Findings Table**: Displays security, bugs, style, and performance issues grouped by category
- ✅ **Severity Badges**: Color-coded severity levels (critical, high, medium, low, info)
- ✅ **CWE Links**: Links to CWE definitions for security findings
- ✅ **Responsive**: Mobile-friendly design with TailwindCSS

## Project Structure

```
src/
├── pages/
│   ├── TriggerReview.tsx    # Input PR URL, submit review
│   └── ReviewDetail.tsx     # Show findings, live SSE updates
├── components/
│   ├── FindingsTable.tsx    # Display findings with details
│   └── StatusBadge.tsx      # Status indicator (pending, analyzing, etc.)
├── hooks/
│   ├── useSSE.ts           # Server-Sent Events streaming
│   └── useNavigate.ts      # Client-side routing
├── api/
│   └── client.ts           # Axios API client + TypeScript types
├── styles/
│   └── globals.css         # TailwindCSS global styles
├── App.tsx                 # Main app, routing logic
└── main.tsx                # React entry point
```

## API Integration

The dashboard proxies requests to the backend via Vite's proxy:

```
/api/v1/* → http://localhost:8000/api/v1/*
```

Make sure the backend is running on port 8000:

```bash
cd ..  # Back to project root
make run
```

## Build

```bash
npm run build   # Production build
npm run preview # Preview production build locally
```

## Technologies

- **React 18**: UI library
- **TypeScript**: Type safety
- **Vite**: Fast build tool
- **TailwindCSS**: Utility-first CSS framework
- **Axios**: HTTP client
- **Lucide React**: Icon library
- **EventSource API**: Server-Sent Events for live updates

## Notes

- The app uses client-side routing (URL rewriting) without React Router
- SSE streams from `/api/v1/sse/reviews/{id}` for real-time progress
- Findings are grouped by category (security, bug_detection, style, performance)
- The dashboard polls `/api/v1/reviews/{id}` every 2 seconds for updates
