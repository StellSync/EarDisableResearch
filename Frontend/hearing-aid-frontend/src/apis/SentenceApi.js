import { api } from "./api.js";

const SentenceApis = {
    startSentences: async function (payload) {
        return await api.post(`/sentence_sessions/start`, payload);
    },
    nextSentence: async function (sessionId) {
        return await api.post(`/sentence_sessions/${sessionId}/next`);
    },
    submitAnswer: async function (sessionId, payload) {
        return await api.post(`/sentence_sessions/${sessionId}/answer`, payload);
    },
    getResults: async function (sessionId) {
        return await api.get(`/sentence_sessions/${sessionId}/result`);
    },
};

export default SentenceApis;
