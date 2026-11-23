import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import JobTable from "../../components/JobTable";

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return { ...actual, useNavigate: () => mockNavigate };
});

const jobs = [
  { id: 1, name: "API Health", task_type: "api_call", rate_limit_per_min: 60, is_active: true, priority: "HIGH" },
  { id: 2, name: "String Job", task_type: "string_manipulation", rate_limit_per_min: 30, is_active: false, priority: "LOW" },
];

function renderTable(data = jobs) {
  return render(
    <MemoryRouter>
      <JobTable jobs={data} />
    </MemoryRouter>
  );
}

describe("JobTable", () => {
  it("renders all column headers", () => {
    renderTable();
    expect(screen.getByText("ID")).toBeInTheDocument();
    expect(screen.getByText("Name")).toBeInTheDocument();
    expect(screen.getByText("Type")).toBeInTheDocument();
    expect(screen.getByText("Priority")).toBeInTheDocument();
    expect(screen.getByText("Rate Limit / min")).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
  });

  it("renders job data correctly", () => {
    renderTable();
    expect(screen.getByText("API Health")).toBeInTheDocument();
    expect(screen.getByText("api_call")).toBeInTheDocument();
    expect(screen.getByText("HIGH")).toBeInTheDocument();
    expect(screen.getByText("LOW")).toBeInTheDocument();
    expect(screen.getByText("60")).toBeInTheDocument();
    expect(screen.getByText("Yes")).toBeInTheDocument();
    expect(screen.getByText("No")).toBeInTheDocument();
  });

  it("navigates to job detail on row click", async () => {
    const user = userEvent.setup();
    renderTable();

    await user.click(screen.getByText("API Health"));

    expect(mockNavigate).toHaveBeenCalledWith("/jobs/1");
  });

  it("shows empty state when no jobs", () => {
    renderTable([]);
    expect(screen.getByText("No jobs yet")).toBeInTheDocument();
    expect(screen.getByText("Create your first job using the form above.")).toBeInTheDocument();
  });

  it("handles null jobs gracefully", () => {
    render(
      <MemoryRouter>
        <JobTable jobs={null} />
      </MemoryRouter>
    );
    // Should render headers but no rows
    expect(screen.getByText("ID")).toBeInTheDocument();
  });

  it("displays active status with green badge", () => {
    renderTable();
    const yes = screen.getByText("Yes");
    expect(yes.closest("span")).toHaveClass("text-green-700");
  });

  it("displays inactive status with red badge", () => {
    renderTable();
    const no = screen.getByText("No");
    expect(no.closest("span")).toHaveClass("text-red-700");
  });
});
