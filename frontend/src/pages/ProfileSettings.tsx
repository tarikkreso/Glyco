import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { api } from "../api/client";
import { useAuth } from "../auth/auth";
import { Card, ErrorState, LoadingState, PageHeader } from "../components/ui";
import { useI18n } from "../i18n";

type ProfileSettingsValues = {
  fullName: string;
  email: string;
  age: number;
  sex: string;
  weight_kg: number;
  height_cm: number;
  high_bp: boolean;
  high_chol: boolean;
  smoker: boolean;
  phys_activity: boolean;
  family_history_diabetes: boolean;
  forecast_personalization_enabled: boolean;
  general_health: number;
};

const fallbackProfile: Omit<ProfileSettingsValues, "fullName" | "email"> = {
  age: 55,
  sex: "Female",
  weight_kg: 86,
  height_cm: 168,
  high_bp: false,
  high_chol: false,
  smoker: false,
  phys_activity: true,
  family_history_diabetes: false,
  forecast_personalization_enabled: true,
  general_health: 3,
};

export function ProfileSettings() {
  const auth = useAuth();
  const { language } = useI18n();
  const userId = auth.session?.userId ?? 1;
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const bs = language === "bs";

  const profileQuery = useQuery({
    queryKey: ["profile", userId],
    queryFn: () => api.profile(userId),
    retry: false,
  });

  const { register, handleSubmit, reset } = useForm<ProfileSettingsValues>({
    defaultValues: {
      fullName: auth.session?.fullName ?? "",
      email: auth.session?.email ?? "",
      ...fallbackProfile,
    },
  });

  useEffect(() => {
    const profile = profileQuery.data;
    reset({
      fullName: auth.session?.fullName ?? "",
      email: auth.session?.email ?? "",
      ...(profile
        ? {
            age: profile.age,
            sex: profile.sex,
            weight_kg: profile.weight_kg,
            height_cm: profile.height_cm,
            high_bp: profile.high_bp,
            high_chol: profile.high_chol,
            smoker: profile.smoker,
            phys_activity: profile.phys_activity,
            family_history_diabetes: profile.family_history_diabetes,
            forecast_personalization_enabled: profile.forecast_personalization_enabled,
            general_health: profile.general_health,
          }
        : fallbackProfile),
    });
  }, [auth.session?.email, auth.session?.fullName, profileQuery.data, reset]);

  return (
    <div className="page narrow">
      <PageHeader title={bs ? "Postavke profila" : "Profile Settings"} subtitle={bs ? "Ažurirajte podatke o računu i zdravstveni profil koji Glyco koristi za rizik, plan njege i kontekst agenta." : "Update account details and the health profile used by Glyco risk, care-plan, and agent context."} />

      <Card title={bs ? "Račun i zdravstveni profil" : "Account and Health Profile"}>
        {profileQuery.isLoading && <LoadingState label={bs ? "Učitavanje profila" : "Loading profile"} />}
        <form
          className="form-stack profile-form-grid"
          onSubmit={handleSubmit(async (values) => {
            setError(null);
            setMessage(null);
            try {
              const user = await api.updateUser(userId, { full_name: values.fullName || "Glyco User", email: values.email });
              const profilePayload = {
                user_id: user.id,
                fruits: true,
                veggies: true,
                stroke_history: false,
                heart_disease_history: false,
                difficulty_walking: false,
                age: values.age,
                sex: values.sex,
                weight_kg: values.weight_kg,
                height_cm: values.height_cm,
                high_bp: values.high_bp,
                high_chol: values.high_chol,
                smoker: values.smoker,
                phys_activity: values.phys_activity,
                family_history_diabetes: values.family_history_diabetes,
                forecast_personalization_enabled: values.forecast_personalization_enabled,
                general_health: values.general_health,
              };
              if (profileQuery.data?.id) {
                await api.updateProfile(profileQuery.data.id, profilePayload);
              } else {
                await api.assessRisk(profilePayload);
              }
              auth.updateSession({ fullName: user.full_name, email: user.email_or_demo_id });
              setMessage(bs ? "Profil je sačuvan. Kontekst rizika će se osvježiti na osnovu ažuriranih podataka." : "Profile saved. Risk context will refresh from the updated data.");
            } catch (error) {
              setError(error instanceof Error ? error.message : (bs ? "Profil nije moguće sačuvati." : "Could not save your profile."));
            }
          })}
        >
          <label className="span-2">{bs ? "Puno ime" : "Full name"}<input type="text" autoComplete="name" {...register("fullName")} /></label>
          <label>{bs ? "Email" : "Email"}<input type="email" autoComplete="email" {...register("email")} /></label>
          <label>{bs ? "Godine" : "Age"}<input type="number" {...register("age", { valueAsNumber: true })} /></label>
          <label>{bs ? "Biološki spol" : "Biological sex"}<select {...register("sex")}><option>{bs ? "Ženski" : "Female"}</option><option>{bs ? "Muški" : "Male"}</option></select></label>
          <label>{bs ? "Težina (kg)" : "Weight (kg)"}<input type="number" step="0.1" {...register("weight_kg", { valueAsNumber: true })} /></label>
          <label>{bs ? "Visina (cm)" : "Height (cm)"}<input type="number" step="0.1" {...register("height_cm", { valueAsNumber: true })} /></label>
          <label>{bs ? "Opšte zdravlje" : "General health"}<select {...register("general_health", { valueAsNumber: true })}><option value={1}>{bs ? "Odlično" : "Excellent"}</option><option value={2}>{bs ? "Vrlo dobro" : "Very good"}</option><option value={3}>{bs ? "Dobro" : "Good"}</option><option value={4}>{bs ? "Zadovoljavajuće" : "Fair"}</option><option value={5}>{bs ? "Loše" : "Poor"}</option></select></label>
          <div className="span-2 check-grid">
            <label className="check"><input type="checkbox" {...register("high_bp")} /> {bs ? "Visok krvni pritisak" : "High blood pressure"}</label>
            <label className="check"><input type="checkbox" {...register("high_chol")} /> {bs ? "Visok holesterol" : "High cholesterol"}</label>
            <label className="check"><input type="checkbox" {...register("family_history_diabetes")} /> {bs ? "Porodična historija dijabetesa" : "Family history of diabetes"}</label>
            <label className="check"><input type="checkbox" {...register("smoker")} /> {bs ? "Trenutni pušač" : "Current smoker"}</label>
            <label className="check"><input type="checkbox" {...register("phys_activity")} /> {bs ? "Fizički aktivan" : "Physically active"}</label>
            <label className="check"><input type="checkbox" {...register("forecast_personalization_enabled")} /> {bs ? "Personalizacija 4h forecasta" : "Personalize 4h forecasts"}</label>
          </div>
          <button className="primary" type="submit">{bs ? "Sačuvaj profil" : "Save Profile"}</button>
        </form>
        {message && <p className="success-note">{message}</p>}
        {(error || profileQuery.isError) && <ErrorState title={bs ? "Problem s profilom" : "Profile issue"} body={error ?? (bs ? "Još nije pronađen sačuvan profil. Spremanje ovog obrasca će ga kreirati." : "No saved profile was found yet. Saving this form will create one.")} />}
      </Card>
    </div>
  );
}
