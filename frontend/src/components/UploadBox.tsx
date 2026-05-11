import { useCallback } from "react";
import { useDropzone } from "react-dropzone";

const ACCEPT = {
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"],
  "application/pdf": [".pdf"],
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
  "text/plain": [".txt"],
};

export function UploadBox({
  onUpload,
  disabled,
}: {
  onUpload: (file: File) => void;
  disabled: boolean;
}) {
  const onDrop = useCallback(
    (accepted: File[]) => {
      if (disabled) return;
      const [file] = accepted;
      if (file) onUpload(file);
    },
    [onUpload, disabled],
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: ACCEPT,
    multiple: false,
    disabled,
  });

  return (
    <div
      {...getRootProps()}
      className={
        "rounded-lg border-2 border-dashed p-4 text-center bg-white cursor-pointer transition " +
        (isDragActive
          ? "border-blue-500 bg-blue-50"
          : "border-gray-300 hover:border-blue-400")
      }
    >
      <input {...getInputProps()} />
      <div className="text-sm text-gray-700">
        {isDragActive ? "Отпустите файл..." : "Загрузите ТЗ"}
      </div>
      <div className="text-xs text-gray-500 mt-1">DOCX, PDF, XLSX, TXT</div>
    </div>
  );
}
