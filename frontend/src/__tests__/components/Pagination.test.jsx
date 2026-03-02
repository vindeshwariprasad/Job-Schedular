import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Pagination from "../../components/Pagination";

describe("Pagination", () => {
  const defaultProps = {
    page: 1,
    size: 20,
    total: 100,
    onPageChange: vi.fn(),
  };

  it("renders nothing when total is 0", () => {
    const { container } = render(<Pagination {...defaultProps} total={0} />);
    expect(container.innerHTML).toBe("");
  });

  it("displays page info correctly", () => {
    render(<Pagination {...defaultProps} />);
    expect(screen.getByText("Page 1 of 5 (100 total)")).toBeInTheDocument();
  });

  it("disables Previous on first page", () => {
    render(<Pagination {...defaultProps} page={1} />);
    expect(screen.getByText("Previous")).toBeDisabled();
  });

  it("disables Next on last page", () => {
    render(<Pagination {...defaultProps} page={5} />);
    expect(screen.getByText("Next")).toBeDisabled();
  });

  it("enables both buttons on middle page", () => {
    render(<Pagination {...defaultProps} page={3} />);
    expect(screen.getByText("Previous")).not.toBeDisabled();
    expect(screen.getByText("Next")).not.toBeDisabled();
  });

  it("calls onPageChange with next page", async () => {
    const user = userEvent.setup();
    render(<Pagination {...defaultProps} page={2} />);

    await user.click(screen.getByText("Next"));

    expect(defaultProps.onPageChange).toHaveBeenCalledWith(3);
  });

  it("calls onPageChange with previous page", async () => {
    const user = userEvent.setup();
    render(<Pagination {...defaultProps} page={3} />);

    await user.click(screen.getByText("Previous"));

    expect(defaultProps.onPageChange).toHaveBeenCalledWith(2);
  });

  it("handles single page correctly", () => {
    render(<Pagination {...defaultProps} total={10} />);
    expect(screen.getByText("Page 1 of 1 (10 total)")).toBeInTheDocument();
    expect(screen.getByText("Previous")).toBeDisabled();
    expect(screen.getByText("Next")).toBeDisabled();
  });
});
