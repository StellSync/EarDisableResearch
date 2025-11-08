import { api } from "./api.js";

const apiDefinitions = {
	startVowels: async function (payload) {
		return await api.post(`/sessions/start`, payload);
	},
	nextVowel: async function (sessionId) {
		return await api.post(`/sessions/${sessionId}/next`);
	},
	submitAnswer: async function (sessionId, payload) {
		return await api.post(`/sessions/${sessionId}/answer`, payload);
	},
	getResults: async function (sessionId) {
		return await api.get(`/sessions/${sessionId}/result`);
	},
};

export default apiDefinitions;
