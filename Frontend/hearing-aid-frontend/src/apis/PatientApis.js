import { api } from "./api.js";

const PatientApis = {
    getPatientResults: async function (user_id) {
        return await api.get(`/doctor/doctor/users/${user_id}/results`);
    },
    getSessionSummary: async function (user_id) {
        return await api.get(`/doctor/doctor/users/${user_id}/sessions`);
    },
    getPatientSummary: async function (user_id) {
        return await api.get(`/doctor/doctor/users/${user_id}/summary`);
    },
    getLastRecordedSession: async function (user_id, type) {
        return await api.get(`/doctor/doctor/users/${user_id}/results?activity=${type}&page_size=1`);
    },
    getSessionSummaryByType: async function (session_id) {
        return await api.get(`/doctor/doctor/session/${session_id}/result`);
    },
};

export default PatientApis;
