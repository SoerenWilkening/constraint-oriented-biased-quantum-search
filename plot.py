import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

from scipy.signal import savgol_filter

def filter_noise(df, length = 40):
	x_filter = savgol_filter(df["oracles"], length, 1)
	y_filter = savgol_filter(df["obj"], length, 1)
	return x_filter, y_filter

def filter_noise2(df, length = 40):
	x_filter = savgol_filter(df["c-time"], length, 1)
	y_filter = savgol_filter(df["obj"], length, 1)
	return x_filter, y_filter

df = pd.read_csv('stores.csv')
exact = df[df["method"] == "QSearch-cpu"].sort_values(by="oracles", ascending=True)
approx = df[df["method"] == "QSearch-gpu"].sort_values(by="oracles", ascending=True)

n = 5000  # the larger n is, the smoother curve will be
b = [1.0 / n] * n
a = 1
# sns.lineplot(exact, x="oracles", y="obj", label = "cpu")
# sns.lineplot(approx, x="oracles", y="obj", label = "gpu")
plt.plot(*filter_noise(exact), label="cpuu", zorder=2)
plt.plot(*filter_noise(approx), label="gpu", zorder=1)
plt.xscale("log")
plt.ylabel("Objective value")
plt.xlabel("Grover iterations")
plt.title("Objective value over time")
plt.legend()
plt.tight_layout()
# plt.savefig("objective_over_time_exact_vs_estimate.pdf")
plt.show()

exact = exact.sort_values(by="c-time", ascending=True)
approx = approx.sort_values(by="c-time", ascending=True)

# sns.lineplot(exact, x="c-time", y="obj", label = "cpu")
# sns.lineplot(approx, x="c-time", y="obj", label = "gpu")
plt.plot(*filter_noise2(exact), label="cpu", zorder=2)
plt.plot(*filter_noise2(approx), label="gpu", zorder=1)
plt.xscale("log")
plt.ylabel("Objective value")
plt.xlabel("benchmarking time")
plt.title("Objective value over time")
plt.legend()
plt.tight_layout()
# plt.savefig("objective_over_time_exact_vs_estimate.pdf")
plt.show()