import { api } from "./api.js";

const ConsonantsApis = {
	startConsonants: async function (payload) {
		return await api.post(`/wiyanjana/start`, payload);
	},
	nextConsonant: async function (sessionId) {
		return await api.get(`/wiyanjana/next/${sessionId}`);
	},
	submitAnswer: async function (payload) {
		return await api.post(`/wiyanjana/choice`, payload);
	},
	getResults: async function (sessionId) {
		return await api.get(`/wiyanjana/session/${sessionId}/result`);
	},
};

export default ConsonantsApis;
