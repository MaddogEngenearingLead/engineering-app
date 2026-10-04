import React from 'react';

export default function Card({ title, children }) {
  return (
    <section className="rounded bg-white p-4 shadow">
      {title && <h2 className="mb-3 text-lg font-semibold">{title}</h2>}
      {children}
    </section>
  );
}
