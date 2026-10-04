import React from 'react';
import Table from './common/Table.jsx';

const COLUMNS = [
  { key: 'tag_id', label: 'Tag', render: (r) => r.tag_id || '(untagged)' },
  { key: 'description', label: 'Description' },
  { key: 'type', label: 'Type' },
  { key: 'quantity', label: 'Qty' },
];
const FULL_COLUMNS = [
  { key: 'item_number', label: '#' },
  ...COLUMNS,
  { key: 'page', label: 'Page' },
  { key: 'location', label: 'Location' },
  { key: 'colour_meaning', label: 'Colour meaning' },
  { key: 'scope_source', label: 'Scope source' },
];

export default function BOMTable({ items = [], limit, full = false }) {
  const rows = limit ? items.slice(0, limit) : items;
  return <Table columns={full ? FULL_COLUMNS : COLUMNS} rows={rows} rowKey={(r, i) => `${r.item_number ?? i}`} empty="No BOM items" />;
}
