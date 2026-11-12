import React, { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { ChevronRight, ShieldCheck, Info, CheckCircle2, ArrowRight } from 'lucide-react';
import Navbar from '../components/Navbar';
import Footer from '../components/Footer';
import { ABOUT_NAV_ITEMS, INFO_PAGES, POLICY_NAV_ITEMS } from '../data/infoPages';

export default function InfoPage({ pageKey }) {
  const page = INFO_PAGES[pageKey] || INFO_PAGES.about;

  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, [pageKey]);

  return (
    <div className="min-h-screen flex flex-col">
      <Navbar />

      <main className="flex-1 max-w-[1240px] w-full mx-auto px-4 py-6 space-y-4">
        {/* Breadcrumb */}
        <nav className="flex items-center gap-1.5 text-xs text-gray-500">
          <Link to="/" className="hover:text-fk-blue font-medium">
            Home
          </Link>
          <ChevronRight className="w-3.5 h-3.5" />
          <span>{page.categoryLabel}</span>
          <ChevronRight className="w-3.5 h-3.5" />
          <span className="text-fk-dark font-semibold">{page.title}</span>
        </nav>

        <div className="flex flex-col md:flex-row gap-4 items-start">
          {/* Left Navigation Sidebar */}
          <aside className="w-full md:w-64 flex-shrink-0 bg-white rounded-sm shadow-sm overflow-hidden">
            <div className="p-4 border-b border-gray-100">
              <h3 className="text-xs font-bold uppercase tracking-wider text-gray-500 flex items-center gap-1.5">
                <Info className="w-3.5 h-3.5 text-fk-blue" /> About Shipkart
              </h3>
              <ul className="mt-2.5 space-y-1">
                {ABOUT_NAV_ITEMS.map((item) => {
                  const active = item.key === pageKey;
                  return (
                    <li key={item.key}>
                      <Link
                        to={item.to}
                        className={`block px-3 py-2 text-xs rounded-sm transition ${
                          active
                            ? 'bg-blue-50 text-fk-blue font-bold border-l-4 border-fk-blue'
                            : 'text-gray-700 hover:bg-gray-50 hover:text-fk-blue'
                        }`}
                      >
                        {item.label}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>

            <div className="p-4">
              <h3 className="text-xs font-bold uppercase tracking-wider text-gray-500 flex items-center gap-1.5">
                <ShieldCheck className="w-3.5 h-3.5 text-fk-blue" /> Consumer Policy
              </h3>
              <ul className="mt-2.5 space-y-1">
                {POLICY_NAV_ITEMS.map((item) => {
                  const active = item.key === pageKey;
                  return (
                    <li key={item.key}>
                      <Link
                        to={item.to}
                        className={`block px-3 py-2 text-xs rounded-sm transition ${
                          active
                            ? 'bg-blue-50 text-fk-blue font-bold border-l-4 border-fk-blue'
                            : 'text-gray-700 hover:bg-gray-50 hover:text-fk-blue'
                        }`}
                      >
                        {item.label}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          </aside>

          {/* Main Content Card */}
          <article className="flex-1 bg-white rounded-sm shadow-sm p-6 md:p-8 space-y-6">
            <header className="border-b border-gray-100 pb-5">
              <span className="inline-block text-[11px] font-bold uppercase tracking-wider text-fk-blue bg-blue-50 px-2.5 py-0.5 rounded">
                {page.categoryLabel}
              </span>
              <h1 className="text-2xl font-bold text-fk-dark mt-2">{page.title}</h1>
              <p className="text-xs text-gray-400 mt-1">Last updated: {page.updatedAt}</p>
              <p className="text-sm text-gray-700 mt-4 leading-relaxed">{page.lead}</p>
            </header>

            <div className="space-y-6">
              {page.sections.map((sec, idx) => (
                <section key={idx} className="space-y-2.5">
                  <h2 className="text-base font-bold text-fk-dark">{sec.heading}</h2>
                  {sec.body && <p className="text-sm text-gray-600 leading-relaxed">{sec.body}</p>}
                  {sec.bullets && (
                    <ul className="space-y-2 pt-1">
                      {sec.bullets.map((bullet, bIdx) => (
                        <li key={bIdx} className="flex items-start gap-2.5 text-sm text-gray-700">
                          <CheckCircle2 className="w-4 h-4 text-fk-green flex-shrink-0 mt-0.5" />
                          <span>{bullet}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </section>
              ))}
            </div>

            {page.cta && (
              <div className="pt-4 border-t border-gray-100">
                <Link
                  to={page.cta.to}
                  className="inline-flex items-center gap-2 bg-fk-orange hover:bg-orange-600 text-white font-bold text-xs px-6 py-3 rounded-sm shadow transition uppercase tracking-wide"
                >
                  <span>{page.cta.label}</span>
                  <ArrowRight className="w-4 h-4" />
                </Link>
              </div>
            )}
          </article>
        </div>
      </main>

      <Footer />
    </div>
  );
}
