import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { TaskFilePicker } from "./TaskFilePicker";

function Picker() {
  const [files, setFiles] = useState<File[]>([]);
  return <TaskFilePicker files={files} onChange={setFiles} />;
}

describe("TaskFilePicker", () => {
  it("lists selected files with sizes and removes an individual file", async () => {
    const user = userEvent.setup();
    render(<Picker />);

    await user.upload(screen.getByLabelText("Files"), [
      new File(["screenshot"], "before.png", { type: "image/png" }),
      new File([new Uint8Array(1536)], "trace.log", { type: "text/plain" }),
    ]);

    expect(screen.getByRole("list", { name: "Selected files" })).toHaveTextContent("before.png");
    expect(screen.getByRole("list", { name: "Selected files" })).toHaveTextContent("10 B");
    expect(screen.getByRole("list", { name: "Selected files" })).toHaveTextContent("trace.log");
    expect(screen.getByRole("list", { name: "Selected files" })).toHaveTextContent("1.5 KB");

    await user.click(screen.getByRole("button", { name: "Remove before.png" }));

    expect(screen.queryByText("before.png")).not.toBeInTheDocument();
    expect(screen.getByText("trace.log")).toBeVisible();
  });
});
