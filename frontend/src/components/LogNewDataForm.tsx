import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { api } from "../api/client";
import { ErrorState } from "./ui";
import { useToast } from "./ui";

export type LogNewDataValues = {
  glucose_level: number;
  is_fasting: "true" | "false";
};

export function LogNewDataForm({
  userId = 1,
  onSuccess,
}: {
  userId?: number;
  onSuccess?: () => void;
}) {
  const queryClient = useQueryClient();
  const toast = useToast();

  const { register, handleSubmit, reset } = useForm<LogNewDataValues>({
    defaultValues: {
      glucose_level: 128,
      is_fasting: "true",
    },
  });

  const addLog = useMutation({
    mutationFn: (values: LogNewDataValues) =>
      api.addLog({
        user_id: userId,
        glucose_level: values.glucose_level,
        is_fasting: values.is_fasting === "true",
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries();
      reset();
      toast({
        tone: "success",
        title: "Saved",
        body: "Your glucose reading was added successfully.",
      });
      onSuccess?.();
    },
  });

  return (
    <>
      <form className="log-form compact-log-form" onSubmit={handleSubmit((values) => addLog.mutate(values))}>
        <label>
          <span>Glucose level</span>
          <input
            type="number"
            inputMode="numeric"
            min={40}
            max={500}
            step={1}
            {...register("glucose_level", { valueAsNumber: true })}
          />
        </label>

        <label>
          <span>Reading type</span>
          <select {...register("is_fasting")}>
            <option value="true">Fasting</option>
            <option value="false">Not fasting</option>
          </select>
        </label>

        <button className="primary" type="submit">
          {addLog.isPending ? "Saving..." : "Save Reading"}
        </button>
      </form>

      {addLog.isError && (
        <ErrorState
          title="Reading could not be saved"
          body={
            addLog.error instanceof Error
              ? addLog.error.message
              : "The monitoring API rejected the new entry. Please try again."
          }
        />
      )}
    </>
  );
}
