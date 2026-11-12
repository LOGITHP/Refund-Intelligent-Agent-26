import React from 'react';
import { Smartphone, Laptop, Shirt, Tv, Sparkles, LayoutGrid } from 'lucide-react';

const CATEGORIES = [
  { id: 'all', label: 'All Products', icon: LayoutGrid },
  { id: 'Mobiles', label: 'Mobiles', icon: Smartphone },
  { id: 'Electronics', label: 'Electronics', icon: Laptop },
  { id: 'Fashion', label: 'Fashion', icon: Shirt },
  { id: 'Appliances', label: 'Appliances', icon: Tv },
];

export default function CategoryBar({ selectedCategory, onSelectCategory }) {
  return (
    <div className="bg-white shadow-sm border-b border-gray-200">
      <div className="max-w-[1240px] mx-auto px-4 flex items-center justify-between overflow-x-auto py-2">
        {CATEGORIES.map((cat) => {
          const Icon = cat.icon;
          const isSelected = selectedCategory === cat.id;
          return (
            <button
              key={cat.id}
              onClick={() => onSelectCategory(cat.id)}
              className={`flex flex-col items-center gap-1 min-w-[90px] py-1 text-xs font-semibold transition motion-reduce:transition-none group ${
                isSelected ? 'text-fk-blue' : 'text-gray-700 hover:text-fk-blue'
              }`}
            >
              <div
                className={`p-2 rounded-full transition-all duration-300 ease-[var(--ease-apple-spring)] motion-reduce:transition-none group-hover:scale-110 ${
                  isSelected
                    ? 'scale-105 bg-blue-50 text-fk-blue'
                    : 'scale-100 bg-gray-100 group-hover:bg-blue-50 group-hover:text-fk-blue text-gray-600'
                }`}
              >
                <Icon className="w-5 h-5" />
              </div>
              <span>{cat.label}</span>
              <span
                aria-hidden="true"
                className={`h-0.5 rounded-full transition-all duration-300 ease-[var(--ease-apple-smooth)] motion-reduce:transition-none ${
                  isSelected ? 'w-10 bg-fk-blue' : 'w-0 bg-transparent'
                }`}
              />
            </button>
          );
        })}
      </div>
    </div>
  );
}

