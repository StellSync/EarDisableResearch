"use client";
import React, { useState, useRef } from "react";
import {
	Dialog,
	DialogContent,
	Typography,
	Button,
	Grid,
	DialogTitle,
} from "@mui/material";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import RestartAltIcon from "@mui/icons-material/RestartAlt";

const QuizDialog = ({ open, onClose, quizType }) => {
	const questions = [
		{
			id: 1,
			question: "ඔයාට කොහොම ද?",
			audioUrl: "/audio/sound1.mp3",
			options: ["Bell", "Horn", "Whistle", "Bird"],
			correctAnswer: "Bell",
		},
		{
			id: 2,
			question: "Identify this musical instrument",
			audioUrl: "/audio/sound2.mp3",
			options: ["Piano", "Guitar", "Drums", "Violin"],
			correctAnswer: "Piano",
		},
	];

	const [currentQuestionIndex, setCurrentQuestionIndex] = useState(0);
	const [selectedAnswer, setSelectedAnswer] = useState("");
	const [score, setScore] = useState(0);
	const [showResults, setShowResults] = useState(false);
	const audioRef = useRef(null);

	const handleAnswerSelect = (answer) => {
		setSelectedAnswer(answer);
	};

	const handlePlayAudio = () => {
		if (audioRef.current) {
			audioRef.current.play();
		}
	};

	const handleSubmit = () => {
		if (selectedAnswer === questions[currentQuestionIndex].correctAnswer) {
			setScore(score + 1);
		}

		if (currentQuestionIndex < questions.length - 1) {
			setCurrentQuestionIndex(currentQuestionIndex + 1);
			setSelectedAnswer("");
		} else {
			setShowResults(true);
		}
	};

	const handleClose = () => {
		setCurrentQuestionIndex(0);
		setScore(0);
		setSelectedAnswer("");
		setShowResults(false);
		onClose();
	};

	const currentQuestion = questions[currentQuestionIndex];

	return (
		<Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
			<DialogTitle>{showResults ? "Quiz Results" : "Hearing Quiz"}</DialogTitle>
			<DialogContent>
				{showResults ? (
					<Grid container spacing={2}>
						<Grid item size={12}>
							<Typography variant="h4" align="center" gutterBottom>
								Your Results
							</Typography>
							<Typography
								variant="h2"
								align="center"
								color="primary"
								gutterBottom
							>
								{score} / {questions.length}
							</Typography>
							<Typography
								variant="body1"
								align="center"
								color="text.secondary"
								gutterBottom
							>
								You got {score} out of {questions.length} questions correct!
							</Typography>
							<Grid container justifyContent="center" sx={{ mt: 3 }}>
								<Button
									variant="contained"
									startIcon={<RestartAltIcon />}
									onClick={handleClose}
								>
									Try Again
								</Button>
							</Grid>
						</Grid>
					</Grid>
				) : (
					<Grid container sx={{ px: 3 }}>
						{/* <Grid item size={12} sx={{ mb: 2 }}>
							<Typography variant="body1" color="text.secondary">
								Question {currentQuestionIndex + 1} of {questions.length} Score:{" "}
								{score}
							</Typography>
						</Grid> */}

						<Grid item xs={12} sx={{ textAlign: "center" }}>
							<Typography variant="h5" sx={{ mb: 2 }}>
								{currentQuestion.question}
							</Typography>
						</Grid>

						<Grid item size={12} sx={{ mb: 3 }}>
							<Button
								variant="contained"
								color="success"
								startIcon={<PlayArrowIcon />}
								onClick={handlePlayAudio}
								sx={{
									borderRadius: 1,
									fontSize: "1rem",
									boxShadow: 3,
									mb: 4,
								}}
							>
								Play Audio
							</Button>
							<audio ref={audioRef} src={currentQuestion.audioUrl} />
						</Grid>

						<Grid item xs={12} sx={{ mb: 3 }}>
							<Grid
								container
								spacing={2}
								justifyContent="center"
								sx={{ maxWidth: "800px", mx: "auto" }}
							>
								{currentQuestion.options.map((option) => (
									<Grid item size={6} key={option}>
										<Button
											fullWidth
											variant="outlined"
											onClick={() => handleAnswerSelect(option)}
											sx={{
												py: 2,
												borderRadius: 1,
												fontSize: "1.1rem",
												minWidth: "120px",
												textTransform: "none",
												borderColor:
													selectedAnswer === option
														? "primary.main"
														: "#e0e0e0",
												color: "primary.main",
												minHeight: "60px",
												backgroundColor: "transparent",
												"&:hover": {
													borderColor: "primary.main",
													backgroundColor: "rgba(25, 118, 210, 0.04)",
												},
											}}
										>
											{option}
										</Button>
									</Grid>
								))}
							</Grid>
						</Grid>

						<Grid
							item
							size={12}
							sx={{ display: "flex", justifyContent: "flex-end" }}
						>
							<Button
								variant="contained"
								onClick={handleSubmit}
								disabled={!selectedAnswer}
								sx={{
									py: 1.5,
									px: 4,
									borderRadius: 1,
									fontSize: "0.9rem",
									opacity: !selectedAnswer ? 0.7 : 1,
									bgcolor: !selectedAnswer ? "#e0e0e0" : "primary.main",
								}}
							>
								{currentQuestionIndex === questions.length - 1
									? "Finish"
									: "Next Question"}
							</Button>
						</Grid>
					</Grid>
				)}
			</DialogContent>
		</Dialog>
	);
};

export default QuizDialog;
