"use client";
import React, { useState } from "react";
import { Typography, Button, Grid, Card, CardContent } from "@mui/material";
import VowelDialog from "../components/VowelDialog";

const Form = () => {
	const [openQuiz, setOpenQuiz] = useState(false);
	const [quizType, setQuizType] = useState("");

	const handleStartQuiz = (type) => {
		setQuizType(type);
		setOpenQuiz(true);
	};

	return (
		<>
			<Grid container sx={{ p: 2 }} direction="column" alignItems="center">
				<Grid item xs={12} sx={{ mb: 4, textAlign: "center" }}>
					<Typography variant="h3" component="h1" gutterBottom>
						Test Your hearing ability
					</Typography>
					<Typography variant="subtitle1" color="text.secondary" sx={{ mb: 4 }}>
						Try 3 test types — quick, accurate, private
					</Typography>
					<Typography variant="body1" color="text.secondary" sx={{ mb: 6 }}>
						Choose a test type to begin. Each test contains several short
						questions and a score that appears after completion.
					</Typography>
				</Grid>

				<Grid
					container
					spacing={4}
					justifyContent="center"
					sx={{ maxWidth: 1200 }}
				>
					<Grid item xs={12} sm={4}>
						<Card
							sx={{
								height: "100%",
								borderRadius: 4,
								transition: "transform 0.2s, box-shadow 0.2s",
								"&:hover": {
									transform: "translateY(-4px)",
									boxShadow: "0 8px 24px rgba(0,0,0,0.12)",
								},
								cursor: "pointer",
							}}
							onClick={() => handleStartQuiz("vowels")}
						>
							<CardContent
								sx={{
									textAlign: "center",
									p: 4,
									display: "flex",
									flexDirection: "column",
									alignItems: "center",
									gap: 2,
									minHeight: 280,
								}}
							>
								<Typography
									variant="h4"
									component="h2"
									gutterBottom
									fontWeight="500"
								>
									Vowels
								</Typography>
								<Typography
									variant="body1"
									color="text.secondary"
									sx={{ mb: 3, fontSize: "1.1rem" }}
								>
									Quick test for vowels recognition
								</Typography>
								<Button
									variant="contained"
									size="large"
									sx={{
										mt: "auto",
										px: 4,
										py: 1.5,
										borderRadius: 3,
										fontSize: "1.1rem",
									}}
								>
									Start
								</Button>
							</CardContent>
						</Card>
					</Grid>

					<Grid item xs={12} sm={4}>
						<Card
							sx={{
								height: "100%",
								borderRadius: 4,
								transition: "transform 0.2s, box-shadow 0.2s",
								"&:hover": {
									transform: "translateY(-4px)",
									boxShadow: "0 8px 24px rgba(0,0,0,0.12)",
								},
								cursor: "pointer",
							}}
							onClick={() => handleStartQuiz("curries")}
						>
							<CardContent
								sx={{
									textAlign: "center",
									p: 4,
									display: "flex",
									flexDirection: "column",
									alignItems: "center",
									gap: 2,
									minHeight: 280,
								}}
							>
								<Typography
									variant="h4"
									component="h2"
									gutterBottom
									fontWeight="500"
								>
									Curries
								</Typography>
								<Typography
									variant="body1"
									color="text.secondary"
									sx={{ mb: 3, fontSize: "1.1rem" }}
								>
									Quick test for curries recognition
								</Typography>
								<Button
									variant="contained"
									size="large"
									sx={{
										mt: "auto",
										px: 4,
										py: 1.5,
										borderRadius: 3,
										fontSize: "1.1rem",
									}}
								>
									Start
								</Button>
							</CardContent>
						</Card>
					</Grid>

					<Grid item xs={12} sm={4}>
						<Card
							sx={{
								height: "100%",
								borderRadius: 4,
								transition: "transform 0.2s, box-shadow 0.2s",
								"&:hover": {
									transform: "translateY(-4px)",
									boxShadow: "0 8px 24px rgba(0,0,0,0.12)",
								},
								cursor: "pointer",
							}}
							onClick={() => handleStartQuiz("sentence")}
						>
							<CardContent
								sx={{
									textAlign: "center",
									p: 4,
									display: "flex",
									flexDirection: "column",
									alignItems: "center",
									gap: 2,
									minHeight: 280,
								}}
							>
								<Typography
									variant="h4"
									component="h2"
									gutterBottom
									fontWeight="500"
								>
									Sentence
								</Typography>
								<Typography
									variant="body1"
									color="text.secondary"
									sx={{ mb: 3, fontSize: "1.1rem" }}
								>
									Quick test for sentence recognition
								</Typography>
								<Button
									variant="contained"
									size="large"
									sx={{
										mt: "auto",
										px: 4,
										py: 1.5,
										borderRadius: 3,
										fontSize: "1.1rem",
									}}
								>
									Start
								</Button>
							</CardContent>
						</Card>
					</Grid>
				</Grid>

				<Grid item xs={12} sx={{ mt: 4, textAlign: "center" }}>
					<Grid container spacing={2} justifyContent="center">
						<Grid item>
							<Typography variant="body2" color="text.secondary">
								Vowels: 100
							</Typography>
						</Grid>
						<Grid item>
							<Typography variant="body2" color="text.secondary">
								Curries: 33
							</Typography>
						</Grid>
						<Grid item>
							<Typography variant="body2" color="text.secondary">
								Sentence: 67
							</Typography>
						</Grid>
					</Grid>
				</Grid>
			</Grid>
			<VowelDialog
				open={openQuiz}
				onClose={() => setOpenQuiz(false)}
				quizType={quizType}
			/>
		</>
	);
};

export default Form;
