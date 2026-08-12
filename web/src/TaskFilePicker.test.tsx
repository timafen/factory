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

    await user.upload(screen.getByLabelText("Файлы"), [
      new File(["screenshot"], "before.png", { type: "image/png" }),
      new File([new Uint8Array(1536)], "trace.log", { type: "text/plain" }),
    ]);

    expect(screen.getByRole("list", { name: "Выбранные файлы" })).toHaveTextContent("before.png");
    expect(screen.getByRole("list", { name: "Выбранные файлы" })).toHaveTextContent("10 B");
    expect(screen.getByRole("list", { name: "Выбранные файлы" })).toHaveTextContent("trace.log");
    expect(screen.getByRole("list", { name: "Выбранные файлы" })).toHaveTextContent("1.5 KB");

    await user.click(screen.getByRole("button", { name: "Удалить before.png" }));

    expect(screen.queryByText("before.png")).not.toBeInTheDocument();
    expect(screen.getByText("trace.log")).toBeVisible();
  });

	it("explains the 5 file and 10 MB limits in Russian", async () => {
		const user = userEvent.setup(); render(<Picker />);
		await user.upload(screen.getByLabelText("Файлы"), Array.from({ length: 6 }, (_, i) => new File(["x"], `${i}.log`)));
		expect(screen.getByText("Можно прикрепить не больше 5 файлов.")).toBeVisible();
		await user.upload(screen.getByLabelText("Файлы"), new File([new Uint8Array(10 * 1024 * 1024 + 1)], "huge.png"));
		expect(screen.getByText("Файл «huge.png» больше 10 МБ.")).toBeVisible();
	});

	it("rejects executable files", async () => {
		const user = userEvent.setup(); render(<Picker />);
		await user.upload(screen.getByLabelText("Файлы"), new File(["x"], "setup.exe"));
		expect(screen.getByText("Файл «setup.exe» исполняемый и не принимается.")).toBeVisible();
	});
});
