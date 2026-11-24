import { useState, useRef, useEffect } from "react";

const MAX_DEPS = 3;

export default function DependencyPicker({ jobs = [], selectedIds = [], onChange }) {
  const [searchTerm, setSearchTerm] = useState("");
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef(null);

  // Close dropdown on outside click
  useEffect(() => {
    const handleClick = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const availableJobs = (jobs || []).filter(
    (j) =>
      j.is_active &&
      !selectedIds.includes(j.id) &&
      j.name.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const selectedJobs = (jobs || []).filter((j) => selectedIds.includes(j.id));

  const addDep = (id) => {
    if (selectedIds.length < MAX_DEPS) {
      onChange([...selectedIds, id]);
    }
    setSearchTerm("");
  };

  const removeDep = (id) => {
    onChange(selectedIds.filter((sid) => sid !== id));
  };

  const atLimit = selectedIds.length >= MAX_DEPS;

  return (
    <div ref={containerRef} className="relative">
      <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
        Depends On (optional)
      </label>

      {/* Selected chips */}
      <div className="flex flex-wrap gap-1.5 mb-1.5">
        {selectedJobs.map((j) => (
          <span
            key={j.id}
            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400 border border-blue-200 dark:border-blue-800"
          >
            #{j.id} {j.name}
            <button
              type="button"
              onClick={() => removeDep(j.id)}
              className="ml-0.5 hover:text-blue-900 dark:hover:text-blue-200"
              aria-label={`Remove dependency on ${j.name}`}
            >
              &times;
            </button>
          </span>
        ))}
      </div>

      {/* Search input */}
      {!atLimit && (
        <input
          type="text"
          placeholder={selectedIds.length === 0 ? "Search jobs to add dependency..." : "Add another dependency..."}
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          onFocus={() => setIsOpen(true)}
          className="w-full border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white p-2 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      )}

      {atLimit && (
        <p className="text-xs text-gray-500 dark:text-gray-400">
          Maximum {MAX_DEPS} dependencies reached
        </p>
      )}

      {/* Dropdown */}
      {isOpen && !atLimit && (
        <div className="absolute z-20 mt-1 w-full bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg max-h-48 overflow-y-auto">
          {availableJobs.length === 0 ? (
            <p className="p-3 text-sm text-gray-500 dark:text-gray-400">
              {searchTerm ? "No matching jobs found" : "No available jobs"}
            </p>
          ) : (
            availableJobs.map((j) => (
              <button
                key={j.id}
                type="button"
                onClick={() => addDep(j.id)}
                className="w-full text-left px-3 py-2 text-sm hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300 border-b border-gray-100 dark:border-gray-700 last:border-0"
              >
                <span className="font-medium text-gray-500 dark:text-gray-400">#{j.id}</span>{" "}
                {j.name}
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}
