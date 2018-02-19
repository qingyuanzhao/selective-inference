from __future__ import print_function
import statsmodels.api as sm
import numpy as np, sys
import regreg.api as rr
from selection.randomized.api import randomization
from selection.adjusted_MLE.selective_MLE import M_estimator_map, solve_UMVU
from selection.algorithms.lasso import lasso
from rpy2 import robjects

import rpy2.robjects.numpy2ri
rpy2.robjects.numpy2ri.activate()

import pandas as pd

def sim_xy(n, p, nval, rho=0, s=5, beta_type=2, snr=1):
    robjects.r('''
    library(bestsubset) #source('~/best-subset/bestsubset/R/sim.R')
    sim_xy = bestsubset::sim.xy
    ''')

    r_simulate = robjects.globalenv['sim_xy']
    sim = r_simulate(n, p, nval, rho, s, beta_type, snr)
    X = np.array(sim.rx2('x'))
    y = np.array(sim.rx2('y'))
    X_val = np.array(sim.rx2('xval'))
    y_val = np.array(sim.rx2('yval'))
    Sigma = np.array(sim.rx2('Sigma'))
    beta = np.array(sim.rx2('beta'))
    sigma = np.array(sim.rx2('sigma'))

    return X, y, X_val, y_val, Sigma, beta, sigma

def tuned_lasso(X, y, X_val,y_val):
    robjects.r('''
        #source('~/best-subset/bestsubset/R/lasso.R')
        tuned_lasso_estimator = function(X,Y,X.val,Y.val){
        Y = as.matrix(Y)
        X = as.matrix(X)
        Y.val = as.vector(Y.val)
        X.val = as.matrix(X.val)
        rel.LASSO = lasso(X,Y,intercept=FALSE, nrelax=10, nlam=50)
        LASSO = lasso(X,Y,intercept=FALSE,nlam=50)
        beta.hat.rellasso = as.matrix(coef(rel.LASSO))
        beta.hat.lasso = as.matrix(coef(LASSO))
        min.lam = min(rel.LASSO$lambda)
        max.lam = max(rel.LASSO$lambda)
        lam.seq = exp(seq(log(max.lam),log(min.lam),length=rel.LASSO$nlambda))
        muhat.val.rellasso = as.matrix(predict(rel.LASSO, X.val))
        muhat.val.lasso = as.matrix(predict(LASSO, X.val))
        err.val.rellasso = colMeans((muhat.val.rellasso - Y.val)^2)
        err.val.lasso = colMeans((muhat.val.lasso - Y.val)^2)
        print(err.val.rellasso)
        opt_lam = ceiling(which.min(err.val.rellasso)/10)
        lambda.tuned = lam.seq[opt_lam]
        return(list(beta.hat.rellasso = beta.hat.rellasso[,which.min(err.val.rellasso)],
        beta.hat.lasso = beta.hat.lasso[,which.min(err.val.lasso)],
        lambda.tuned = lambda.tuned, lambda.seq = lam.seq))
        }''')

    r_lasso = robjects.globalenv['tuned_lasso_estimator']

    n, p = X.shape
    nval, _ = X_val.shape
    r_X = robjects.r.matrix(X, nrow=n, ncol=p)
    r_y = robjects.r.matrix(y, nrow=n, ncol=1)
    r_X_val = robjects.r.matrix(X_val, nrow=nval, ncol=p)
    r_y_val = robjects.r.matrix(y_val, nrow=nval, ncol=1)

    tuned_est = r_lasso(r_X, r_y, r_X_val, r_y_val)
    estimator_rellasso = np.array(tuned_est.rx2('beta.hat.rellasso'))
    estimator_lasso = np.array(tuned_est.rx2('beta.hat.lasso'))
    lam_tuned = np.array(tuned_est.rx2('lambda.tuned'))
    lam_seq = np.array(tuned_est.rx2('lambda.seq'))
    return estimator_rellasso, estimator_lasso, lam_tuned, lam_seq

def relative_risk(est, truth, Sigma):

    return (est-truth).T.dot(Sigma).dot(est-truth)/truth.T.dot(Sigma).dot(truth)

def comparison_risk_inference(n=500, p=100, nval=500, rho=0.35, s=5, beta_type=2, snr=0.2,
                              randomization_scale=np.sqrt(0.25), target="partial"):

    while True:
        ##extract tuned relaxed LASSO and LASSO estimator
        X, y, X_val, y_val, Sigma, beta, sigma = sim_xy(n=n, p=p, nval=nval, rho=rho, s=s, beta_type=beta_type, snr=snr)
        true_mean = X.dot(beta)
        rel_LASSO, est_LASSO, lam_tuned, lam_seq = tuned_lasso(X, y, X_val, y_val)

        active_nonrand = (rel_LASSO != 0)
        nactive_nonrand = active_nonrand.sum()

        X -= X.mean(0)[None, :]
        X /= (X.std(0)[None, :] * np.sqrt(n))

        X_val -= X_val.mean(0)[None, :]
        X_val /= (X_val.std(0)[None, :] * np.sqrt(nval))

        if p > n:
            sigma_est = np.std(y)
            print("sigma and sigma_est", sigma, sigma_est)
        else:
            ols_fit = sm.OLS(y, X).fit()
            sigma_est = np.linalg.norm(ols_fit.resid) / np.sqrt(n - p - 1.)
            print("sigma and sigma_est", sigma, sigma_est)

        _y = y
        y = y - y.mean()
        y /= sigma_est
        y_val = y_val - y_val.mean()
        y_val /= sigma_est

        true_mean /= sigma_est

        if target == "debiased":
            M = np.linalg.inv(Sigma)
        else:
            M = np.identity(p)

        ##tune randomized LASSO
        loss = rr.glm.gaussian(X, y)
        epsilon = 1. / np.sqrt(n)
        lam_seq = np.linspace(0.75, 2.75, num=100) * np.mean(
            np.fabs(np.dot(X.T, np.random.standard_normal((n, 2000)))).max(0))
        err = np.zeros(100)
        randomizer = randomization.isotropic_gaussian((p,), scale=randomization_scale)
        for k in range(100):
            lam = lam_seq[k]
            W = np.ones(p) * lam
            penalty = rr.group_lasso(np.arange(p), weights=dict(zip(np.arange(p), W)), lagrange=1.)
            M_est = M_estimator_map(loss, epsilon, penalty, randomizer, M,
                                    target=target, randomization_scale=randomization_scale, sigma=1.)

            active = M_est._overall
            nactive = active.sum()
            approx_MLE_est = np.zeros(p)
            if nactive > 0:
                M_est.solve_map()
                approx_MLE = solve_UMVU(M_est.target_transform,
                                        M_est.opt_transform,
                                        M_est.target_observed,
                                        M_est.feasible_point,
                                        M_est.target_cov,
                                        M_est.randomizer_precision)[0]
                approx_MLE_est[active] = approx_MLE

            err[k] = np.mean((y_val - X_val.dot(approx_MLE_est)) ** 2.)

        lam = lam_seq[np.argmin(err)]
        sys.stderr.write("lambda from tuned relaxed LASSO" + str(lam_tuned) + "\n")
        sys.stderr.write("lambda from randomized LASSO" + str(lam) + "\n")

        ##run tuned randomized LASSO
        W = np.ones(p) * lam
        penalty = rr.group_lasso(np.arange(p), weights=dict(zip(np.arange(p), W)), lagrange=1.)
        M_est = M_estimator_map(loss, epsilon, penalty, randomizer, M, target=target,
                                randomization_scale=randomization_scale, sigma=1.)
        active = M_est._overall
        nactive = np.sum(active)

        ##run non-randomized version of LASSO
        LASSO_py = lasso.gaussian(X, y, np.asscalar(lam_tuned), sigma=1.)
        soln = LASSO_py.fit()
        Con = LASSO_py.constraints
        active_LASSO = (soln != 0)
        nactive_LASSO = active_LASSO.sum()
        active_LASSO_signs = np.sign(soln[active_LASSO])

        sys.stderr.write("number of variables selected by randomized LASSO" + str(nactive) + "\n")
        sys.stderr.write("number of variables selected by tuned LASSO" + str(nactive_nonrand) + "\n")
        sys.stderr.write("number of variables selected by tuned LASSO py" + str(nactive_LASSO) + "\n"+ "\n")

        if target == "partial":
            true_target = np.linalg.inv(X[:, active].T.dot(X[:, active])).dot(X[:, active].T).dot(true_mean)
            unad_sd =  np.sqrt(np.diag(np.linalg.inv(X[:, active].T.dot(X[:, active]))))
            true_target_nonrand = np.linalg.inv(X[:, active_nonrand].T.dot(X[:, active_nonrand])). \
                dot(X[:, active_nonrand].T).dot(true_mean)
            unad_sd_nonrand = np.sqrt(np.diag(np.linalg.inv(X[:, active_nonrand].T.dot(X[:, active_nonrand]))))
            true_target_LASSO = np.linalg.inv(X[:, active_LASSO].T.dot(X[:, active_LASSO])).\
                dot(X[:, active_LASSO].T).dot(true_mean)
        elif target == "full":
            X_full_inv = np.linalg.pinv(X)
            true_target = X_full_inv[active].dot(true_mean)
            unad_sd = np.sqrt(np.diag(X_full_inv[active].dot(X_full_inv[active].T)))
            true_target_nonrand = X_full_inv[active_nonrand].dot(true_mean)
            unad_sd_nonrand = np.sqrt(np.diag(X_full_inv[active_nonrand].dot(X_full_inv[active_nonrand].T)))
            true_target_LASSO = X_full_inv[active_LASSO].dot(true_mean)
        elif target == "debiased":
            X_full_inv = M.dot(X.T)
            true_target = X_full_inv[active].dot(true_mean)
            unad_sd = np.sqrt(np.diag(X_full_inv[active].dot(X_full_inv[active].T)))
            true_target_nonrand = X_full_inv[active_nonrand].dot(true_mean)
            unad_sd_nonrand = np.sqrt(np.diag(X_full_inv[active_nonrand].dot(X_full_inv[active_nonrand].T)))
            true_target_LASSO = X_full_inv[active_LASSO].dot(true_mean)

        true_signals = np.zeros(p, np.bool)
        true_signals[beta != 0] = 1
        screened_randomized = np.logical_and(active, true_signals).sum() / float(s)
        screened_nonrandomized = np.logical_and(active_nonrand, true_signals).sum() / float(s)
        false_positive_randomized = np.logical_and(active, ~true_signals).sum() / max(float(nactive), 1.)
        false_positive_nonrandomized = np.logical_and(active_nonrand, ~true_signals).sum() / max(float(nactive_nonrand),
                                                                                                 1.)
        true_set = np.asarray([u for u in range(p) if true_signals[u]])
        active_set = np.asarray([t for t in range(p) if active[t]])
        active_set_nonrand = np.asarray([q for q in range(p) if active_nonrand[q]])
        active_bool = np.zeros(nactive, np.bool)
        for x in range(nactive):
            active_bool[x] = (np.in1d(active_set[x], true_set).sum() > 0)
        active_bool_nonrand = np.zeros(nactive_nonrand, np.bool)
        for w in range(nactive_nonrand):
            active_bool_nonrand[w] = (np.in1d(active_set_nonrand[w], true_set).sum() > 0)

        active_set_LASSO = np.asarray([q for q in range(p) if active_LASSO[q]])
        active_bool_LASSO = np.zeros(nactive_LASSO, np.bool)
        for z in range(nactive_LASSO):
            active_bool_LASSO[z] = (np.in1d(active_set_LASSO[z], true_set).sum() > 0)

        coverage_sel = 0.
        coverage_Lee = 0.
        coverage_rand = 0.
        coverage_nonrand = 0.

        power_sel = 0.
        power_Lee = 0.
        power_rand = 0.
        power_nonrand = 0.

        length_sel = 0.
        length_Lee = 0.
        length_rand = 0.
        length_nonrand = 0.

        if nactive > 0 and nactive_LASSO > 0:

            for k in range(nactive_nonrand):

                if ((np.sqrt(n) * rel_LASSO[k] / sigma_est) - (1.65 * unad_sd_nonrand[k])) <= true_target_nonrand[k] \
                        and ((np.sqrt(n) * rel_LASSO[k] / sigma_est) + (1.65 * unad_sd_nonrand[k])) >= \
                                true_target_nonrand[k]:
                    coverage_nonrand += 1
                length_nonrand +=  sigma_est* 2* 1.65 * unad_sd_nonrand[k]
                if active_bool_nonrand[k] == True and (
                        ((np.sqrt(n) * rel_LASSO[k] / sigma_est) - (1.65 * unad_sd_nonrand[k])) > 0.
                or ((np.sqrt(n) * rel_LASSO[k] / sigma_est) + (1.65 * unad_sd_nonrand[k])) < 0.):
                    power_nonrand += 1

            M_est.solve_map()
            approx_MLE, var, mle_map, _, _, mle_transform = solve_UMVU(M_est.target_transform,
                                                                       M_est.opt_transform,
                                                                       M_est.target_observed,
                                                                       M_est.feasible_point,
                                                                       M_est.target_cov,
                                                                       M_est.randomizer_precision)

            approx_sd = np.sqrt(np.diag(var))
            mle_target_lin, mle_soln_lin, mle_offset = mle_transform

            if nactive == 1:
                approx_MLE = np.array([approx_MLE])
                approx_sd = np.array([approx_sd])

            for j in range(nactive):
                if (approx_MLE[j] - (1.65 * approx_sd[j])) <= true_target[j] and \
                                (approx_MLE[j] + (1.65 * approx_sd[j])) >= true_target[j]:
                    coverage_sel += 1
                length_sel += sigma_est * 2 * 1.65 * approx_sd[j]
                if active_bool[j] == True and (
                                (approx_MLE[j] - (1.65 * approx_sd[j])) > 0. or (
                                    approx_MLE[j] + (1.65 * approx_sd[j])) < 0.):
                    power_sel += 1

                if (M_est.target_observed[j] - (1.65 * unad_sd[j])) <= true_target[j] and (
                            M_est.target_observed[j] + (1.65 * unad_sd[j])) >= true_target[j]:
                    coverage_rand += 1
                length_rand += sigma_est * 2 * 1.65 * unad_sd[j]
                if active_bool[j] == True and ((M_est.target_observed[j] - (1.65 * unad_sd[j])) > 0. or (
                            M_est.target_observed[j] + (1.65 * unad_sd[j])) < 0.):
                    power_rand += 1

            Lee = LASSO_py.summary('twosided', alpha=0.10, compute_intervals=True)
            Lee_lc = np.asarray(Lee['lower_confidence'])
            Lee_uc = np.asarray(Lee['upper_confidence'])

            for l in range(nactive_LASSO):
                if (Lee_lc[l] <= true_target_LASSO[l]) and (true_target_LASSO[l] <= Lee_uc[l]):
                    coverage_Lee += 1
                length_Lee += sigma_est* (Lee_uc[l] - Lee_lc[l])

                if active_bool_LASSO[l] == True and (Lee_lc[l] > 0. or Lee_uc[l] < 0.):
                    power_Lee += 1

            break

    target_par = beta

    ind_est = np.zeros(p)
    ind_est[active] = (mle_target_lin.dot(M_est.target_observed) +
                       mle_soln_lin.dot(M_est.observed_opt_state[:nactive]) + mle_offset)
    ind_est /= (np.sqrt(n) * (1. / sigma_est))

    relaxed_Lasso = np.zeros(p)
    relaxed_Lasso[active] = M_est.target_observed / (np.sqrt(n) * (1. / sigma_est))

    Lasso_est = np.zeros(p)
    Lasso_est[active] = M_est.observed_opt_state[:nactive] / (np.sqrt(n) * (1. / sigma_est))

    selective_MLE = np.zeros(p)
    selective_MLE[active] = approx_MLE / (np.sqrt(n) * (1. / sigma_est))

    padded_true_target = np.zeros(p)
    padded_true_target[active] = true_target

    if True:
        return (selective_MLE - padded_true_target).sum() / float(nactive),\
               relative_risk(selective_MLE, target_par, Sigma), \
               relative_risk(relaxed_Lasso, target_par, Sigma), \
               relative_risk(ind_est, target_par, Sigma), \
               relative_risk(Lasso_est, target_par, Sigma), \
               relative_risk(rel_LASSO, target_par, Sigma), \
               relative_risk(est_LASSO, target_par, Sigma), \
               screened_randomized, \
               screened_nonrandomized, \
               false_positive_randomized, \
               false_positive_nonrandomized, \
               coverage_sel / max(float(nactive), 1.), \
               coverage_Lee / max(float(nactive_LASSO), 1.), \
               coverage_rand / max(float(nactive), 1.), \
               coverage_nonrand / max(float(nactive_nonrand), 1.), \
               power_sel / float(s), \
               power_Lee / float(s), \
               power_rand / float(s), \
               power_nonrand / float(s),\
               length_sel / max(float(nactive), 1.), \
               length_Lee / max(float(nactive_LASSO), 1.), \
               length_rand / max(float(nactive), 1.), \
               length_nonrand / max(float(nactive_nonrand), 1.)


if __name__ == "__main__":

    columns = ["bias", "risk_selMLE", "risk_relLASSO", "risk_indest", "risk_LASSO", "risk_relLASSO_nonrand", "risk_LASSO_nonrand"
               "spower_rand", "spower_nonrand", "false_positive_randomized", "false_positive_nonrandomized",
               "coverage_sel", "coverage_Lee", "coverage_rand", "coverage_nonrand",
               "power_sel", "power_Lee", "power_rand", "power_nonrand",
               "length_sel", "length_Lee", "length_rand", "length_nonrand"]

    df_master = pd.DataFrame()

    ndraw = 1
    bias = 0.
    risk_selMLE = 0.
    risk_relLASSO = 0.
    risk_indest = 0.
    risk_LASSO = 0.
    risk_relLASSO_nonrand = 0.
    risk_LASSO_nonrand = 0.
    spower_rand = 0.
    spower_nonrand = 0.
    false_positive_randomized = 0.
    false_positive_nonrandomized = 0.
    coverage_sel = 0.
    coverage_Lee = 0.
    coverage_rand = 0.
    coverage_nonrand = 0.
    power_sel = 0.
    power_rand = 0.
    power_nonrand = 0.
    power_Lee = 0.
    length_sel = 0.
    length_Lee = 0.
    length_rand = 0.
    length_nonrand = 0.

    for i in range(ndraw):
        approx = comparison_risk_inference(n=200, p=50, nval=200, rho=0.35, s=10,
                                           beta_type=2, snr=0.05, target="full")
        if approx is not None:
            bias += approx[0]
            risk_selMLE += approx[1]
            risk_relLASSO += approx[2]
            risk_indest += approx[3]
            risk_LASSO += approx[4]
            risk_relLASSO_nonrand += approx[5]
            risk_LASSO_nonrand += approx[6]

            spower_rand += approx[7]
            spower_nonrand += approx[8]
            false_positive_randomized += approx[9]
            false_positive_nonrandomized += approx[10]

            coverage_sel += approx[11]
            coverage_Lee += approx[12]
            coverage_rand += approx[13]
            coverage_nonrand += approx[14]

            power_sel += approx[15]
            power_Lee += approx[16]
            power_rand += approx[17]
            power_nonrand += approx[18]

            length_sel += approx[19]
            length_Lee += approx[20]
            length_rand += approx[21]
            length_nonrand += approx[22]

            metrics = pd.DataFrame()
            metric = metrics.assign(bias = approx[0],
                                    risk_selMLE = approx[1],
                                    risk_relLASSO = approx[2],
                                    risk_indest = approx[3],
                                    risk_LASSO = approx[4],
                                    risk_relLASSO_nonrand = approx[5],
                                    risk_LASSO_nonrand = approx[6],
                                    spower_rand = approx[7],
                                    spower_nonrand = approx[8],
                                    false_positive_randomized = approx[9],
                                    false_positive_nonrandomized = approx[10],
                                    coverage_sel = approx[11],
                                    coverage_Lee = approx[12],
                                    coverage_rand = approx[13],
                                    coverage_nonrand = approx[14],
                                    power_sel = approx[15],
                                    power_Lee = approx[16],
                                    power_rand = approx[17],
                                    power_nonrand = approx[18],
                                    length_sel = approx[19],
                                    length_Lee = approx[20],
                                    length_rand = approx[21],
                                    length_nonrand = approx[22])

            df_master = df_master.append(metrics, ignore_index=True)

        sys.stderr.write("overall_bias" + str(bias / float(i + 1)) + "\n")
        sys.stderr.write("overall_selrisk" + str(risk_selMLE / float(i + 1)) + "\n")
        sys.stderr.write("overall_relLASSOrisk" + str(risk_relLASSO / float(i + 1)) + "\n")
        sys.stderr.write("overall_indepestrisk" + str(risk_indest / float(i + 1)) + "\n")
        sys.stderr.write("overall_LASSOrisk" + str(risk_LASSO / float(i + 1)) + "\n")
        sys.stderr.write("overall_relLASSOrisk_norand" + str(risk_relLASSO_nonrand / float(i + 1)) + "\n")
        sys.stderr.write("overall_LASSOrisk_norand" + str(risk_LASSO_nonrand / float(i + 1)) + "\n"+"\n")

        # sys.stderr.write("overall_LASSO_rand_spower" + str(spower_rand / float(i + 1)) + "\n")
        # sys.stderr.write("overall_LASSO_norand_spower" + str(spower_nonrand / float(i + 1)) + "\n")
        # sys.stderr.write("overall_LASSO_rand_falsepositives" + str(false_positive_randomized / float(i + 1)) + "\n")
        # sys.stderr.write("overall_LASSO_norand_falsepositives" + str(false_positive_nonrandomized / float(i + 1)) + "\n"+"\n")

        sys.stderr.write("selective coverage" + str(coverage_sel / float(i + 1)) + "\n")
        sys.stderr.write("Lee coverage" + str(coverage_Lee / float(i + 1)) + "\n")
        sys.stderr.write("randomized coverage" + str(coverage_rand / float(i + 1)) + "\n")
        sys.stderr.write("nonrandomized coverage" + str(coverage_nonrand / float(i + 1)) + "\n"+"\n")

        sys.stderr.write("selective power" + str(power_sel / float(i + 1)) + "\n")
        sys.stderr.write("Lee power" + str(power_Lee / float(i + 1)) + "\n")
        sys.stderr.write("randomized power" + str(power_rand / float(i + 1)) + "\n")
        sys.stderr.write("nonrandomized power" + str(power_nonrand / float(i + 1)) + "\n"+"\n")

        sys.stderr.write("selective length" + str(length_sel / float(i + 1)) + "\n")
        sys.stderr.write("Lee length" + str(length_Lee / float(i + 1)) + "\n")
        sys.stderr.write("randomized length" + str(length_rand / float(i + 1)) + "\n")
        sys.stderr.write("nonrandomized length" + str(length_nonrand / float(i + 1)) + "\n" + "\n")

        sys.stderr.write("iteration completed" + str(i) + "\n" +"\n")

    df_master.to_csv("/Users/snigdhapanigrahi/adjusted_MLE/results/...csv", index=False)