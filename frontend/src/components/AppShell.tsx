import React, { useState } from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import {
  HelpCircle,
  CheckCircle2,
  Share2,
  FolderOpen,
  PanelLeftClose,
  PanelLeftOpen,
  Database,
  Menu,
  X,
} from 'lucide-react';
import { ThemeToggle } from './ThemeToggle';

export const AppShell: React.FC = () => {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const navItems = [
    { to: '/', label: 'Ask', icon: HelpCircle },
    { to: '/decisions', label: 'Decisions', icon: CheckCircle2 },
    { to: '/graph', label: 'Graph', icon: Share2 },
    { to: '/sources', label: 'Sources', icon: FolderOpen },
  ];

  return (
    <div className="min-h-screen flex flex-col md:flex-row bg-bg text-text">
      {/* Skip to main content link for screen-readers & keyboard navigation */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:top-3 focus:left-3 focus:z-50 focus:px-4 focus:py-2 focus:bg-primary focus:text-white focus:rounded-control"
      >
        Skip to content
      </a>

      {/* Mobile top bar (visible below 768px) */}
      <header className="md:hidden flex items-center justify-between px-4 py-3 bg-surface border-b border-border">
        <div className="flex items-center gap-2">
          {/* Small circle-and-line glyph */}
          <svg
            width="18"
            height="18"
            viewBox="0 0 18 18"
            fill="none"
            aria-hidden="true"
            className="shrink-0"
          >
            <circle cx="5" cy="9" r="3.5" stroke="var(--color-primary)" strokeWidth="2" />
            <line x1="8.5" y1="9" x2="16" y2="9" stroke="var(--color-primary)" strokeWidth="2" strokeLinecap="round" />
          </svg>
          <span className="font-semibold text-sm tracking-tight text-text">
            Decision Trace
          </span>
        </div>

        <div className="flex items-center gap-2">
          <ThemeToggle />
          <button
            type="button"
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="p-2 rounded-control text-text-muted hover:text-text hover:bg-surface-subtle border border-border"
            aria-label={mobileMenuOpen ? 'Close navigation menu' : 'Open navigation menu'}
          >
            {mobileMenuOpen ? <X className="w-4 h-4" /> : <Menu className="w-4 h-4" />}
          </button>
        </div>
      </header>

      {/* Mobile menu dropdown */}
      {mobileMenuOpen && (
        <nav
          className="md:hidden bg-surface border-b border-border px-4 py-2 space-y-1"
          aria-label="Mobile navigation"
        >
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                onClick={() => setMobileMenuOpen(false)}
                className={({ isActive }) =>
                  `flex items-center gap-2.5 px-3 py-2 rounded-control text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-surface-subtle text-text border border-primary/60 font-semibold'
                      : 'text-text-muted hover:text-text hover:bg-surface-subtle border border-transparent'
                  }`
                }
              >
                <Icon className="w-4 h-4 shrink-0" aria-hidden="true" />
                <span>{item.label}</span>
              </NavLink>
            );
          })}
        </nav>
      )}

      {/* Desktop Left Sidebar (240px or collapsed to 64px) */}
      <aside
        className={`hidden md:flex flex-col border-r border-border bg-surface transition-all duration-150 ease-in-out shrink-0 ${
          isCollapsed ? 'w-16' : 'w-[240px]'
        }`}
        aria-label="Sidebar navigation"
      >
        {/* Wordmark & Collapse Toggle */}
        <div className="flex items-center justify-between px-4 h-14 border-b border-border">
          {!isCollapsed && (
            <div className="flex items-center gap-2 overflow-hidden">
              {/* Plain circle-and-line glyph */}
              <svg
                width="18"
                height="18"
                viewBox="0 0 18 18"
                fill="none"
                aria-hidden="true"
                className="shrink-0"
              >
                <circle cx="5" cy="9" r="3.5" stroke="var(--color-primary)" strokeWidth="2" />
                <line x1="8.5" y1="9" x2="16" y2="9" stroke="var(--color-primary)" strokeWidth="2" strokeLinecap="round" />
              </svg>
              <span className="font-semibold text-sm tracking-tight text-text whitespace-nowrap">
                Decision Trace
              </span>
            </div>
          )}

          <button
            type="button"
            onClick={() => setIsCollapsed(!isCollapsed)}
            className={`p-1.5 rounded-control text-text-muted hover:text-text hover:bg-surface-subtle border border-transparent hover:border-border transition-colors ${
              isCollapsed ? 'mx-auto' : ''
            }`}
            title={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            aria-label={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {isCollapsed ? (
              <PanelLeftOpen className="w-4 h-4" />
            ) : (
              <PanelLeftClose className="w-4 h-4" />
            )}
          </button>
        </div>

        {/* Navigation items */}
        <nav className="flex-1 p-2 space-y-1" aria-label="Main application sections">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-3 py-2 rounded-control text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-surface-subtle text-text border border-primary/60 font-semibold'
                      : 'text-text-muted hover:text-text hover:bg-surface-subtle border border-transparent'
                  } ${isCollapsed ? 'justify-center px-2' : ''}`
                }
                title={isCollapsed ? item.label : undefined}
              >
                <Icon className="w-4 h-4 shrink-0" aria-hidden="true" />
                {!isCollapsed && <span>{item.label}</span>}
              </NavLink>
            );
          })}
        </nav>

        {/* Sidebar Footer */}
        <div className="p-3 border-t border-border bg-surface-subtle text-xs text-text-muted">
          {!isCollapsed ? (
            <div className="flex items-center gap-2">
              <Database className="w-3.5 h-3.5 text-primary shrink-0" aria-hidden="true" />
              <div className="truncate">
                <span className="block font-medium text-text">Dataset</span>
                <span className="font-mono text-[11px] text-text-muted">company_brain</span>
              </div>
            </div>
          ) : (
            <div className="flex justify-center" title="Dataset: company_brain">
              <Database className="w-4 h-4 text-primary" aria-hidden="true" />
            </div>
          )}
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Desktop Top Bar */}
        <header className="hidden md:flex items-center justify-between px-6 h-14 bg-surface border-b border-border">
          <div className="flex items-center gap-2 text-xs text-text-muted">
            <span className="font-medium text-text">Dataset:</span>
            <span className="font-mono px-2 py-0.5 rounded-control bg-surface-subtle border border-border text-text">
              company_brain
            </span>
            <span className="text-text-muted">·</span>
            <span>Frozen graph</span>
          </div>

          <div className="flex items-center gap-3">
            <ThemeToggle />
          </div>
        </header>

        {/* Page View with skip-to landmark */}
        <main id="main-content" className="flex-1 p-4 md:p-6 max-w-7xl w-full mx-auto" tabIndex={-1}>
          <Outlet />
        </main>
      </div>
    </div>
  );
};
