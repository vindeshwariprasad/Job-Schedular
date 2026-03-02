import React from "react";
import JsonView from "@uiw/react-json-view";
import { useTheme } from "../context/ThemeContext";

export default function JsonViewer({ data }) {
  const { theme } = useTheme();

  if (!data) {
    return (
      <p className="text-gray-500 dark:text-gray-400 text-sm">
        No payload available
      </p>
    );
  }

  return (
    <JsonView
      value={data}
      collapsed={false}
      enableClipboard={true}
      displayDataTypes={false}
      style={{
        fontSize: 14,
        backgroundColor: "transparent",
        color: theme === "dark" ? "#e5e7eb" : undefined,
      }}
    />
  );
}
