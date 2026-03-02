import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ConfirmModal from "../../components/ConfirmModal";

describe("ConfirmModal", () => {
  const defaultProps = {
    open: true,
    title: "Delete Item",
    message: "Are you sure you want to delete this?",
    onConfirm: vi.fn(),
    onCancel: vi.fn(),
  };

  it("renders nothing when closed", () => {
    const { container } = render(<ConfirmModal {...defaultProps} open={false} />);
    expect(container.innerHTML).toBe("");
  });

  it("renders title and message when open", () => {
    render(<ConfirmModal {...defaultProps} />);
    expect(screen.getByText("Delete Item")).toBeInTheDocument();
    expect(screen.getByText("Are you sure you want to delete this?")).toBeInTheDocument();
  });

  it("renders custom button labels", () => {
    render(
      <ConfirmModal {...defaultProps} confirmLabel="Yes, Delete" cancelLabel="No, Keep" />
    );
    expect(screen.getByText("Yes, Delete")).toBeInTheDocument();
    expect(screen.getByText("No, Keep")).toBeInTheDocument();
  });

  it("defaults to Confirm and Cancel labels", () => {
    render(<ConfirmModal {...defaultProps} />);
    expect(screen.getByText("Confirm")).toBeInTheDocument();
    expect(screen.getByText("Cancel")).toBeInTheDocument();
  });

  it("calls onConfirm when confirm button clicked", async () => {
    const user = userEvent.setup();
    render(<ConfirmModal {...defaultProps} />);

    await user.click(screen.getByText("Confirm"));

    expect(defaultProps.onConfirm).toHaveBeenCalledTimes(1);
  });

  it("calls onCancel when cancel button clicked", async () => {
    const user = userEvent.setup();
    render(<ConfirmModal {...defaultProps} />);

    await user.click(screen.getByText("Cancel"));

    expect(defaultProps.onCancel).toHaveBeenCalledTimes(1);
  });

  it("calls onCancel when backdrop clicked", async () => {
    const user = userEvent.setup();
    const { container } = render(<ConfirmModal {...defaultProps} />);
    const backdrop = container.querySelector(".bg-gray-900\\/60");

    await user.click(backdrop);

    expect(defaultProps.onCancel).toHaveBeenCalled();
  });

  it("disables buttons when loading", () => {
    render(<ConfirmModal {...defaultProps} loading={true} />);

    expect(screen.getByText("Cancel")).toBeDisabled();
    expect(screen.getByText("Confirm")).toBeDisabled();
  });

  it("shows spinner when loading", () => {
    const { container } = render(<ConfirmModal {...defaultProps} loading={true} />);
    expect(container.querySelector(".animate-spin")).toBeInTheDocument();
  });

  it("renders danger variant", () => {
    const { container } = render(<ConfirmModal {...defaultProps} variant="danger" />);
    expect(container.querySelector(".bg-red-100")).toBeInTheDocument();
  });

  it("renders warning variant", () => {
    const { container } = render(<ConfirmModal {...defaultProps} variant="warning" />);
    expect(container.querySelector(".bg-amber-100")).toBeInTheDocument();
  });

  it("renders info variant", () => {
    const { container } = render(<ConfirmModal {...defaultProps} variant="info" />);
    expect(container.querySelector(".bg-blue-100")).toBeInTheDocument();
  });
});
