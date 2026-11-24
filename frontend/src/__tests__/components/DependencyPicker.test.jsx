import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import DependencyPicker from "../../components/DependencyPicker";

const jobs = [
  { id: 1, name: "Job Alpha", is_active: true },
  { id: 2, name: "Job Beta", is_active: true },
  { id: 3, name: "Job Gamma", is_active: true },
  { id: 4, name: "Job Delta", is_active: false },
];

describe("DependencyPicker", () => {
  it("renders label", () => {
    render(<DependencyPicker jobs={jobs} selectedIds={[]} onChange={vi.fn()} />);
    expect(screen.getByText("Depends On (optional)")).toBeInTheDocument();
  });

  it("renders search input when no deps selected", () => {
    render(<DependencyPicker jobs={jobs} selectedIds={[]} onChange={vi.fn()} />);
    expect(screen.getByPlaceholderText("Search jobs to add dependency...")).toBeInTheDocument();
  });

  it("shows available active jobs in dropdown on focus", async () => {
    const user = userEvent.setup();
    render(<DependencyPicker jobs={jobs} selectedIds={[]} onChange={vi.fn()} />);

    await user.click(screen.getByPlaceholderText("Search jobs to add dependency..."));

    expect(screen.getByText("Job Alpha")).toBeInTheDocument();
    expect(screen.getByText("Job Beta")).toBeInTheDocument();
    expect(screen.getByText("Job Gamma")).toBeInTheDocument();
    // Inactive job should not appear
    expect(screen.queryByText("Job Delta")).not.toBeInTheDocument();
  });

  it("filters jobs by search term", async () => {
    const user = userEvent.setup();
    render(<DependencyPicker jobs={jobs} selectedIds={[]} onChange={vi.fn()} />);

    const input = screen.getByPlaceholderText("Search jobs to add dependency...");
    await user.click(input);
    await user.type(input, "Alpha");

    expect(screen.getByText("Job Alpha")).toBeInTheDocument();
    expect(screen.queryByText("Job Beta")).not.toBeInTheDocument();
  });

  it("calls onChange when a job is selected", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<DependencyPicker jobs={jobs} selectedIds={[]} onChange={onChange} />);

    await user.click(screen.getByPlaceholderText("Search jobs to add dependency..."));
    await user.click(screen.getByText("Job Alpha"));

    expect(onChange).toHaveBeenCalledWith([1]);
  });

  it("renders selected job as chip", () => {
    render(<DependencyPicker jobs={jobs} selectedIds={[1]} onChange={vi.fn()} />);
    expect(screen.getByText(/#1 Job Alpha/)).toBeInTheDocument();
  });

  it("calls onChange to remove when chip X is clicked", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<DependencyPicker jobs={jobs} selectedIds={[1]} onChange={onChange} />);

    await user.click(screen.getByLabelText("Remove dependency on Job Alpha"));

    expect(onChange).toHaveBeenCalledWith([]);
  });

  it("shows max limit message when 3 deps selected", () => {
    render(<DependencyPicker jobs={jobs} selectedIds={[1, 2, 3]} onChange={vi.fn()} />);
    expect(screen.getByText("Maximum 3 dependencies reached")).toBeInTheDocument();
    expect(screen.queryByPlaceholderText(/Search/)).not.toBeInTheDocument();
  });

  it("excludes already-selected jobs from dropdown", async () => {
    const user = userEvent.setup();
    render(<DependencyPicker jobs={jobs} selectedIds={[1]} onChange={vi.fn()} />);

    await user.click(screen.getByPlaceholderText("Add another dependency..."));

    expect(screen.queryByText("Job Alpha")).not.toBeInTheDocument();
    expect(screen.getByText("Job Beta")).toBeInTheDocument();
  });

  it("handles empty jobs list gracefully", async () => {
    const user = userEvent.setup();
    render(<DependencyPicker jobs={[]} selectedIds={[]} onChange={vi.fn()} />);

    await user.click(screen.getByPlaceholderText("Search jobs to add dependency..."));

    expect(screen.getByText("No available jobs")).toBeInTheDocument();
  });
});
