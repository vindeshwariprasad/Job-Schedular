import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ThemeProvider } from "../../context/ThemeContext";
import JsonViewer from "../../components/JsonViewer";

function renderWithTheme(ui) {
  return render(<ThemeProvider>{ui}</ThemeProvider>);
}

describe("JsonViewer", () => {
  it("shows placeholder when data is null", () => {
    renderWithTheme(<JsonViewer data={null} />);
    expect(screen.getByText("No payload available")).toBeInTheDocument();
  });

  it("shows placeholder when data is undefined", () => {
    renderWithTheme(<JsonViewer data={undefined} />);
    expect(screen.getByText("No payload available")).toBeInTheDocument();
  });

  it("renders JSON data", () => {
    renderWithTheme(<JsonViewer data={{ url: "https://example.com", method: "GET" }} />);
    expect(screen.getByText(/https:\/\/example\.com/)).toBeInTheDocument();
    expect(screen.getByText(/GET/)).toBeInTheDocument();
  });
});
